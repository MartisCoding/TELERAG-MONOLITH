"""
This is an updated version of the so-called "Scrapper" class, which is responsible for collecting messages from Telegram channels.
This version includes improvements in the code structure, error handling, and logging.

Main differences:
1. Improved error handling: The code now includes more specific error handling for different exceptions that may occur during the message collection process.
2. Enhanced logging: The logging messages have been improved to provide more context and clarity about the actions being performed.
3. Reimagined class logic: Now the class does not STORE its messages. Instead, when we have a request in a "RetrievalAugmentedResponse" Object we add to this object newly gathered messages.

Also, this message handling may increase load on api. To ensure that we do not exceed the limits, we have to add a channel caching.
It is not straight storing, rather TTL (Time To Live) cache, which will store the last channels that have been requested.
"""

from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.errors import PeerIdInvalid, ChatAdminRequired, ChatWriteForbidden, UserAlreadyParticipant

from source.ChromaАndRAG.ChromaDBHelper import ChromaDBHelper
from source.TelegramMessageScrapper.exceptions import *
from source.MiddleWareResponseModels import RetrievalAugmentedResponse
from source.Logging import get_logger

class TeleRagCrawler:
    """
    The TeleRagCrawler class is responsible for collecting messages from Telegram channels.
    It uses the Pyrogram library to interact with the Telegram API and handle incoming messages.
    """

    def __init__(self, api_id: str, api_hash: str, history_limit: int, chroma: ChromaDBHelper):
        self.pyro_client = Client(
            name="TELERAG-MessageScrapper",
            api_id=api_id,
            api_hash=api_hash
        )
        self.chroma_db_helper = None # Placeholder for the ChromaDBHelper instance soon will be added.
        self._channels = set() # This stores channel ids. Instead of getting chat. We will have all subbed channels here.
        self.database_helper = None # Placeholder for the database helper soon will add.
        # We will not process the channel if the collection in chroma already exists in a pending state.
        self.crawler_logger = get_logger("Crawler", "network")
        self.history_limit = history_limit
        self.chroma = chroma

    async def add_channel(self, channel_name: str):
        """
        This one subscribes to the channel and adds it to the list of channels.
        """
        # Since pyrogram does not support direct ids, we need to get channel by its name.
        try:
            chat = await self.pyro_client.get_chat(channel_name)
            if chat.type == ChatType.CHANNEL:
                await self.pyro_client.join_chat(channel_name)
                self._channels.add(channel_name)
        except PeerIdInvalid:
            self.crawler_logger.error(f"Peer ID is invalid. {channel_name}")
            raise CrawlerCannotSubscribe(f"Cannot subscribe to the channel. Invalid peer ID. {channel_name}")
        except ChatAdminRequired:
            raise CrawlerCannotSubscribe(f"Cannot subscribe to the channel. Admin rights required. {channel_name}")
        except ChatWriteForbidden:
            raise CrawlerCannotSubscribe(f"Cannot subscribe to the channel. Write permission required. {channel_name}")
        except UserAlreadyParticipant:
            self.crawler_logger.warning(f"Bot is already participant. {channel_name}")
            raise CrawlerAlreadySubscribed(f"Already subscribed to the channel. {channel_name}")

    async def remove_channel(self, channel_name: str):
        if channel_name not in self._channels:
            raise CrawlerCannotUnsubscribe(f"Cannot unsubscribe to the channel. Not present in subscribed {channel_name}")
        try:
            await self.pyro_client.leave_chat(channel_name)
            self._channels.remove(channel_name)
        except PeerIdInvalid:
            self.crawler_logger.error(f"Peer ID is invalid. {channel_name}")
            raise CrawlerCannotUnsubscribe(f"Cannot unsubscribe to the channel. Invalid peer ID. {channel_name}")

    async def process_response(self, response: RetrievalAugmentedResponse):
        """
        This method will process the response and add the messages to the response object.
        """
        self.crawler_logger.info(f"Caught response from {response.user_name} with query: {response.query}")

        channel_names = response.channel_names
        results = {}
        if not channel_names:
            self.crawler_logger.critical("Critical error. No channels provided for processing.")
            return CrawlerChannelInvalid("No channels provided for processing.")
        for channel_name in channel_names:
            if channel_name not in self._channels:
                self.crawler_logger.error("Channel not found in subscribed channels.")
                return CrawlerChannelInvalid("Channel not found in subscribed channels.")
            if self.chroma.acknowledge(channel_name):
                results[channel_name] = []
                continue
            results[channel_name] = []
            try:
                async for message in self.pyro_client.get_chat_history(channel_name, limit=self.history_limit):
                    if message.text:
                        results[channel_name].append(message.text)
            except PeerIdInvalid:
                self.crawler_logger.critical(f"Peer ID is invalid. {channel_name}")
                return CrawlerChannelInvalid("Invalid peer ID.")

        response.channels_and_messages = results
        response.set_next(self.chroma.process_response)


    async def start(self):
        """
        Starts the Pyrogram client and begins listening for messages.
        """
        self.crawler_logger.info("Starting the crawler.")
        await self.pyro_client.start()

    async def stop(self):
        """
        Stops the Pyrogram client and disconnects from Telegram.
        """
        self.crawler_logger.info("Stopping the crawler.")
        await self.pyro_client.stop()




