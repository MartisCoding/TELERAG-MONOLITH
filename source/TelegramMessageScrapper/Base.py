"""
This is base file where the collector is defined. The collection logic lies in the collector.py file.
"""
import asyncio
import enum
from pyrogram import Client, filters
from pyrogram.enums import ChatType
from dataclasses import dataclass
from source.Core import Logger, CoreMultiprocessing, Task, CoreException, Injectable
from typing import Any, Dict, List
scrapper_logger = Logger("Scrapper", "network.log")

class ScrapSIG(enum.Enum):
    SUB = 0
    UNSUB = 1

@dataclass
class ChannelRecord:
    channel_id: int
    action: ScrapSIG

class Scrapper(Injectable):
    """
    The logic is that the bot accepts new channel_ids, if channels database was updated (new channel added or deleted)
    """

    class ScrapperException(CoreException):
        pass

    def __init__(self, api_id: str, api_hash: str, history_limit: int):
        self.pyro_client = Client(
            name="TELERAG-MessageScrapper",
            api_id=api_id,
            api_hash=api_hash
        )
        self.channels_and_messages: Dict[int, List[str]] = {}
        self.message_hist_limit = history_limit
        self.message_handler = None
        self.new_message_queue = asyncio.Queue()
        self.getting_messages_event = asyncio.Event()
        self.running = True

    def update(self, records: List[ChannelRecord]) -> None:
        """
        Creates an update task for the scrapper.
        """
        if not self.running:
            return
        task = Task(
            func=self._update,
            args=(records,),
            name="Scrapper.update"
        )
        CoreMultiprocessing.push_task(task)

    async def _update(self, record: List[ChannelRecord]) -> None:
        """
        Updates the state of scrapper by adding or deleting channels.
        """
        # Validate if the channel_id is channel and not user or group
        if not self.running:
            return

        await scrapper_logger.debug("Got update request... Updating channels...")
        for record in record:
            try:
                chat = await self.pyro_client.get_chat(record.channel_id)
                if chat.type != ChatType.CHANNEL:
                    raise self.ScrapperException(
                        where="Scrapper.update()",
                        what="Invalid channel type",
                        summary=f"Channel {record.channel_id} is not a channel.",
                    )
                if record.action == ScrapSIG.SUB:
                    if record.channel_id in self.channels_and_messages.keys():
                        raise self.ScrapperException(
                            where="Scrapper.update()",
                            what="Channel already subscribed, while trying to subscribe",
                            summary=f"Channel {record.channel_id} is already subscribed.",
                        )
                    await self.pyro_client.join_chat(record.channel_id)
                    self.channels_and_messages[record.channel_id] = []
                    await self.fetch(record.channel_id)
                    await self.update_or_create_message_handler()
                elif record.action == ScrapSIG.UNSUB:
                    if record.channel_id not in self.channels_and_messages.keys():
                        raise self.ScrapperException(
                            where="Scrapper.update()",
                            what="Channel not subscribed, while trying to unsubscribe",
                            summary=f"Channel {record.channel_id} is not subscribed.",
                        )
                    await self.pyro_client.leave_chat(record.channel_id)
                    self.channels_and_messages[record.channel_id].clear()
                    del self.channels_and_messages[record.channel_id]
                    await self.update_or_create_message_handler()
            except self.ScrapperException as e:
                await scrapper_logger.warning("An error occurred while updating the scrapper: " + str(e) + "Skipping this channel.")


    async def fetch(self, channel_id: int):
        """
        Fetches the messages from the channel.
        """
        if not self.running:
            return
        msgs = []
        if channel_id not in self.channels_and_messages.keys():
            raise self.ScrapperException(
                where="Scrapper.fetch()",
                what="Channel not subscribed",
                summary=f"Got unsubscribed channel id: {channel_id}. Try to subscribe first.",
            )
        try:
            async for message in self.pyro_client.get_chat_history(channel_id, limit=self.message_hist_limit):
                if message.text:
                    msgs.append(message.text)
                else:
                    await scrapper_logger.debug(f"Message {message.message_id} in channel {channel_id} is not a text message. Skipping.")
        except Exception as e:
            await scrapper_logger.warning(f"An error occurred while fetching messages from channel {channel_id}: {e}")
        finally:
            if msgs:
                self.channels_and_messages[channel_id].extend(msgs)
                await scrapper_logger.debug(f"Fetched {len(msgs)} messages from channel {channel_id}.")
            else:
                await scrapper_logger.debug(f"No messages fetched from channel {channel_id}.")

    async def update_or_create_message_handler(self) -> None:
        """
        Updates PyroGram's message handler. If not created, creates a new one.
        """
        if not self.channels_and_messages.keys():
            raise self.ScrapperException(
                where="Scrapper.update_or_create_message_handler()",
                what="Nothing to create.",
                summary="Channels pool is empty. Nothing to create."
            )

        if self.message_handler:
            self.pyro_client.remove_handler(self.message_handler)
            self.message_handler = None

        @self.pyro_client.on_message(filters.chat(list(self.channels_and_messages.keys())))
        async def message_handler(message: Any) -> None:
            """
            Handles the incoming messages from the channels.
            """
            if message.text:
                self.channels_and_messages[message.chat.id].append(message.text)
                if self.getting_messages:
                    await self.new_message_queue.put((message.chat.id, message.text))
                await scrapper_logger.debug(f"Got new message from channel {message.chat.id}: {message.text}")
            else:
                await scrapper_logger.debug(f"Message {message.message_id} in channel {message.chat.id} is not a text message. Skipping.")

        if not self.getting_messages_event.is_set():
            self.getting_messages_event.set()

        self.message_handler = message_handler

    async def __aiter__(self):
        self._existing_messages_iter = iter(self.channels_and_messages.items())
        self._current_channel_id = None
        self._current_message_iter = None
        return self

    async def __anext__(self):
        while self._existing_messages_iter:
            if self._current_message_iter is None:
                try:
                    self._current_channel_id, messages = next(self._existing_messages_iter)
                    self._current_message_iter = iter(messages)
                except StopIteration:
                    break
            try:
                return self._current_channel_id, next(self._current_message_iter)
            except StopIteration:
                self._current_message_iter = None

        channel_id, msg = await self.new_message_queue.get()
        if msg is None:
            raise StopAsyncIteration
        return channel_id, msg

    async def scrapper_start(self):
        """
        The main loop of the scrapper. It runs in a separate process and handles the incoming messages.
        """
        await self.pyro_client.start()
        await scrapper_logger.debug("Scrapper started.")
        self.running = True

    async def scrapper_stop(self):
        """
        Stops the scrapper.
        """
        await self.pyro_client.stop()
        await scrapper_logger.debug("Scrapper stopped.")
        self.running = False

