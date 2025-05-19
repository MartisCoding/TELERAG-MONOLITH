from typing import List, Optional, Set, Tuple
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorDatabase,
    AsyncIOMotorCollection
)

from pymongo.errors import CollectionInvalid
from source.Logging import Logger
from source.Database.MongoHelperModels import UserModel, ChannelModel
from source.Database.exceptions import *
import asyncio

from source.TelegramMessageScrapper import Crawler
from source.TelegramMessageScrapper.exceptions import *
from source.Logging import get_logger

class MongoDBHelper:
    def __init__(self, db: AsyncIOMotorDatabase, crawler: Crawler):
        self.db = db
        self.crawler = crawler
        self.mongo_db_logger = get_logger("MongoDB", "network")
        self.users: AsyncIOMotorCollection = db["users"]
        self.channels: AsyncIOMotorCollection = db["channels"]

    @classmethod
    def create(
        cls,
        crawler: Crawler,
        uri: str = "",
        db_name: str = "",
    ) -> "MongoDBHelper":
        client = AsyncIOMotorClient(uri)
        db = client[db_name]
        self = cls(db, crawler)
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError as e:
            raise RuntimeError("No running event loop found.") from e
        asyncio.run_coroutine_threadsafe(self._setup(), loop).result()
        return self

    async def _setup(self) -> None:
        collections = await self.db.list_collection_names()
        if "users" not in collections:
            try:
                await self.db.create_collection("users")
            except CollectionInvalid:
                self.mongo_db_logger.info(f"Skipping collection creation. Collection 'users' already exists")
        if "channels" not in collections:
            try:
                await self.db.create_collection("channels")
            except CollectionInvalid:
                self.mongo_db_logger.info(f"Skipping collection creation. Collection 'channels' already exists")


    async def create_user(self, user_id: int, name: str) -> None:
        if await self.users.find_one({"_id": user_id}):
            raise UserAlreadyExists
        user = UserModel(
            name=name,
            id=user_id,
        )
        await self.users.insert_one(user.model_dump(by_alias=True))
        self.mongo_db_logger.info(f"Created user '{name}' with id {user_id}")

    async def get_user(self, user_id: int) -> Optional[UserModel]:
        user = await self.users.find_one({"_id": user_id})
        if not user:
            raise UserNotFound
        return UserModel.model_validate(user)

    async def delete_user(self, user_id: int) -> None:
        user_doc = await self.users.find_one({"_id": user_id})
        if not user_doc:
            raise UserNotFound
        user = UserModel(**user_doc)
        for channel_id in user.channels:
            try:
                await self.decrement_channel(channel_id)
            except CannotEndTransaction as e:
                self.mongo_db_logger.critical(f'Error in decrementing channel {channel_id} for user {user_id}: {e}')
                raise CannotEndTransaction(f"Cannot perform transaction due to error in crawler synchronisation: {e}") from e
        await self.users.delete_one({"_id": user_id})
        self.mongo_db_logger.info(f"Deleted user '{user_id}'")

    async def create_channel(self, channel_id: int, name: str) -> None:
        channel_doc = await self.channels.find_one({"_id": channel_id})
        if channel_doc:
            raise ChannelAlreadyExists
        else:
            try:
                self.mongo_db_logger.info(f'Notifying crawler about new channel {name}')
                self.crawler.add_channel(channel_id, name)
                self.mongo_db_logger.info(f'Crawler notified about new channel {name}')
                # Now the transaction will not end UNTIL the crawler subscribed.
                self.db.insert_one(ChannelModel(
                    id=channel_id,
                    name=name,
                ).model_dump(by_alias=True))
                self.mongo_db_logger.info(f"Created channel '{name}' with id {channel_id}")
            except CrawlerCannotSubscribe as e:
                # This is a critical error. We cannot perform transaction.
                self.mongo_db_logger.critical(f'Crawler could not subscribe to channel {name}: {e}')
                raise CannotEndTransaction(f"Cannot perform transaction due to error in crawler synchronisation: {e}") from e
            except CrawlerAlreadySubscribed as e:
                self.mongo_db_logger.warning(f"Crawler already subscribed to channel {name}: {e}")
                # Though here we can perform transaction. It's just synchronisation with crawler.
                self.db.insert_one(ChannelModel(
                    id=channel_id,
                    name=name,
                ).model_dump(by_alias=True
                ))

    async def delete_channel(self, channel_id: int, name: str) -> None:
        channel_doc = await self.channels.find_one({"_id": channel_id})
        if not channel_doc:
            raise ChannelNotFound
        channel = ChannelModel(**channel_doc)
        if channel.subscribers > 0:
            raise ChannelHasSubscribers

        try:
            self.mongo_db_logger.info(f'Notifying crawler about channel {name} deletion')
            await self.crawler.remove_channel(name)
            self.mongo_db_logger.info(f'Crawler notified about channel {name} deletion')
            await self.db.delete_one({"_id": channel_id})
            self.mongo_db_logger.info(f"Deleted channel '{name}' with id {channel_id}")
        except CrawlerCannotUnsubscribe as e:
            # This is a critical error. We cannot perform transaction.
            self.mongo_db_logger.critical(f'Crawler could not unsubscribe from channel {name}: {e}')
            raise CannotEndTransaction(f"Cannot perform transaction due to error in crawler synchronisation: {e}") from e

    async def get_channel(self, channel_id: int) -> Optional[ChannelModel]:
        channel_doc = await self.channels.find_one({"_id": channel_id})
        if not channel_doc:
            raise ChannelNotFound
        return ChannelModel(**channel_doc)

    async def increment_channel(self, channel_id: int):
        channel_doc = await self.channels.find_one({"_id": channel_id})
        if not channel_doc:
            raise ChannelNotFound
        await self.channels.update_one({"_id": channel_id}, {"$inc": {"subscribers": 1}})

    async def decrement_channel(self, channel_id: int):
        channel_doc = await self.channels.find_one({"_id": channel_id})
        if not channel_doc:
            raise ChannelNotFound
        channel = ChannelModel(**channel_doc)
        try:
            if channel.subscribers - 1 <= 0:
                await self.delete_channel(channel.id, channel.name)
            else:
                await self.channels.update_one({"_id": channel_id}, {"$inc": {"subscribers": -1}})
        except CannotEndTransaction as e:
            raise e

    async def add_for_user(self, user_id: int, channel_id: int):
        user_doc = await self.users.find_one({"_id": user_id})
        if not user_doc:
            raise UserNotFound
        user = UserModel(**user_doc)
        channel_doc = await self.channels.find_one({"_id": channel_id})
        if not channel_doc:
            raise ChannelNotFound
        channel = ChannelModel(**channel_doc)
        if channel_id in user.channels:
            raise ChannelsAlreadyPresentInUser
        user.channels[channel.id] = channel.name
        self.mongo_db_logger.info(f"Added channel '{channel.name}' to channel '{channel.name}'")
        await self.channels.update_one({"_id": channel_id}, {"$inc": {"subscribers": 1}})
        await self.users.replace_one({"_id": user_id}, user.model_dump(by_alias=True))

    async def remove_for_user(self, user_id: int, channel_id):
        user_doc = await self.users.find_one({"_id": user_id})
        if not user_doc:
            raise UserNotFound
        user = UserModel(**user_doc)
        if channel_id not in user.channels:
            raise ChannelsNotPresentInUser
        try:
            await self.decrement_channel(channel_id)
        except CannotEndTransaction as e:
            self.mongo_db_logger.critical(f'Error in decrementing channel {channel_id} for user {user_id}: {e}')
            raise e
        except ChannelNotFound as e:
            self.mongo_db_logger.critical(f'Channel not found for user {user_id}: {e}')
            raise e

