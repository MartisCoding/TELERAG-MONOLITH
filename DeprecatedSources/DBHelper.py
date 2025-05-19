from typing import List, Optional, Set
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorDatabase,
    AsyncIOMotorCollection
)

from pymongo.errors import CollectionInvalid
from source.Logging import Logger

from DeprecatedSources.Models import UserModel, ChannelModel


class DataBaseHelper:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.mongo_db_logger = Logger("MongoDB", "network.log")
        self.db = db
        self.users: AsyncIOMotorCollection = db["users"]
        self.channels: AsyncIOMotorCollection = db["channels"]


    @classmethod
    async def create(
        cls,
        uri: str = "",
        db_name: str = "",
    ) -> "DataBaseHelper":
        client = AsyncIOMotorClient(uri)
        db = client[db_name]
        self = cls(db)
        await self._setup()
        await self.mongo_db_logger.info("MongoDB connected")
        return self

    async def _setup(self) -> None:
        collections = await self.db.list_collection_names()
        if "users" not in collections:
            try:
                await self.db.create_collection("users")
            except CollectionInvalid:
                await self.mongo_db_logger.warning("Collection 'users' already exists")
        if "channels" not in collections:
            try:
                await self.db.create_collection("channels")
            except CollectionInvalid:
                await self.mongo_db_logger.warning("Collection 'channels' already exists")

    async def create_user(self, user_id: int, name: str) -> None:
        if await self.users.find_one({"_id": user_id}):
            await self.mongo_db_logger.warning(f"User '{user_id}' already exists")
            raise ValueError("User already exists")
        user = UserModel(
            name=name,
            _id=user_id,
        )
        await self.users.insert_one(user.dict(by_alias=True))

    async def delete_user(self, user_id: int) -> None:
        user_doc = await self.users.find_one({"_id": user_id})
        if not user_doc:
            await self.mongo_db_logger.warning(f"User '{user_id}' not found")
            raise ValueError("User not found")

        user = UserModel(**user_doc)
        for channel_id in user.channels:
            await self._decrement_channel(channel_id)

        await self.users.delete_one({"_id": user_id})

    async def update_user_channels(
        self,
        user_id: int,
        add: Optional[List[int]] = None,
        remove: Optional[List[int]] = None
    ) -> None:
        doc = await self.users.find_one({"_id": user_id})
        if not doc:
            raise ValueError("User not found")

        user = UserModel(**doc)
        current: Set[int] = set(user.channels)
        to_add = set(add or [])
        to_remove = set(remove or [])

        for ch in to_add:
            if not await self.channels.find_one({"_id": ch}):
                raise ValueError(f"Channel {ch} does not exist")

        for ch in to_add - current:
            await self._increment_channel(ch)
        for ch in to_remove & current:
            await self._decrement_channel(ch)

        updated = (current | to_add) - to_remove
        user.channels = list(updated)

        await self.users.replace_one(
            {"_id": user_id},
            user.dict(by_alias=True)
        )

    async def get_user(self, user_id: int) -> UserModel:
        doc = await self.users.find_one({"_id": user_id})
        if not doc:
            raise ValueError("User not found")
        return UserModel(**doc)

    async def create_channel(self, channel_id: int, name: str) -> None:
        if await self.channels.find_one({"_id": channel_id}):
            await self.mongo_db_logger.warning(f"Channel '{channel_id}' already exists. Will not create one.")
            raise ValueError("Channel already exists")
        print("Created channel " + str(name))
        channel = ChannelModel(_id=channel_id, name=name)
        await self.channels.insert_one(channel.dict(by_alias=True))



    async def delete_channel(self, channel_id: int) -> None:
        doc = await self.channels.find_one({"_id": channel_id})
        if not doc:
            raise ValueError("Channel not found")

        if doc["subscribers"] > 0:
            raise ValueError("Channel has subscribers")

        await self.channels.delete_one({"_id": channel_id})


    async def get_channel(self, channel_id: int) -> ChannelModel:
        doc = await self.channels.find_one({"id": channel_id})
        if not doc:
            raise ValueError("Channel not found")
        return ChannelModel(**doc)

    async def _increment_channel(self, channel_id: int) -> None:
        await self.channels.update_one(
            {"_id": channel_id},
            {"$inc": {"subscribers": 1}}
        )

    async def _decrement_channel(self, channel_id: int) -> None:
        doc = await self.channels.find_one({"_id": channel_id})
        if not doc:
            return

        if doc["subscribers"] <= 1:
            await self.channels.delete_one({"_id": channel_id})
        else:
            await self.channels.update_one(
                {"id": channel_id},
                {"$inc": {"subscribers": -1}}
            )



