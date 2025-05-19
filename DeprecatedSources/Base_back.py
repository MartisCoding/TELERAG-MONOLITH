"""
This is base file where the collector is defined. The collection logic lies in the collector.py file.
"""
import asyncio
import enum
from pyrogram import Client, filters
from pyrogram.enums import ChatType
from dataclasses import dataclass
from source.Logging import Logger
from typing import Any, Dict, List, Tuple
from pyrogram.errors import PeerIdInvalid, ChatAdminRequired, ChatWriteForbidden, UserAlreadyParticipant


class Scrapper:
    """
    The logic is that the bot accepts new channel_ids, if channels database was updated (new channel added or deleted)
    """

    class ScrapperException(Exception):
        pass

    def __init__(self, api_id: str, api_hash: str, history_limit: int):

        self.pyro_client = Client(
            name="TELERAG-MessageScrapper",
            api_id=api_id,
            api_hash=api_hash
        )
        self.channels_and_messages: Dict[int, Tuple[str, List[str]]] = {}
        self.message_hist_limit = history_limit
        self.message_handler = None
        self.new_message_queue = asyncio.Queue()
        self.getting_messages_event = asyncio.Event()
        self.running = True


    async def update(self, records: List[ChannelRecord]) -> None:
        """
        Creates an update task for the scrapper.
        """
        if not self.running:
            return
        await self._update(records)

    async def _update(self, records: List[ChannelRecord]) -> None:
        """
        Updates the state of scrapper by adding or deleting channels.
        """
        # Validate if the id is channel and not user or group
        if not self.running:
            return

        await self.scrapper_logger.debug("Got update request... Updating channels...")
        for records in records:
            try:
                try:
                    print(f"Trying to get chat {records.channel_id}")
                    chat = await self.pyro_client.get_chat(records.channel_id)
                except Exception as e:
                    try:
                        print(f"Trying to join then get chat {records.channel_id}")
                        await self.pyro_client.join_chat(records.channel_id)
                        chat = await self.pyro_client.get_chat(records.channel_id)
                    except (PeerIdInvalid, ChatAdminRequired, ChatWriteForbidden, UserAlreadyParticipant, Exception) as e:
                        print("Error while joining chat: ", e)
                        raise ValueError("Error while joining chat: " + str(e))

                if chat.type != ChatType.CHANNEL:
                    await self.pyro_client.leave_chat(records.channel_id)
                    raise ValueError("Channel ID is not a channel")
                if records.action == ScrapSIG.SUB:
                    if records.channel_id in self.channels_and_messages.keys():
                        raise ValueError("Channel already subscribed")
                    self.channels_and_messages[records.channel_id] = (chat.title, [])
                    await self.fetch(records.channel_id)
                    await self.update_or_create_message_handler()
                elif records.action == ScrapSIG.UNSUB:
                    if records.channel_id not in self.channels_and_messages.keys():
                        raise ValueError("Channel not subscribed")
                    await self.pyro_client.leave_chat(records.channel_id)
                    self.channels_and_messages[records.channel_id][1].clear()
                    del self.channels_and_messages[records.channel_id]
                    await self.update_or_create_message_handler()
            except self.ScrapperException as e:
                await self.scrapper_logger.warning("An error occurred while updating the scrapper: " + str(e) + "Skipping this channel.")


    async def fetch(self, channel_id: int):
        """
        Fetches the messages from the channel.
        """
        if not self.running:
            return
        msgs = []
        if channel_id not in self.channels_and_messages.keys():
            raise ValueError("Channel not subscribed")
        try:
            async for message in self.pyro_client.get_chat_history(channel_id, limit=self.message_hist_limit):
                if message.text:
                    msgs.append(message.text)
                else:
                    await self.scrapper_logger.debug(f"Message {message.message_id} in channel {channel_id} is not a text message. Skipping.")
        except Exception as e:
            await self.scrapper_logger.warning(f"An error occurred while fetching messages from channel {channel_id}: {e}")
        finally:
            if msgs:
                self.channels_and_messages[channel_id][1].extend(msgs)
                await self.scrapper_logger.debug(f"Fetched {len(msgs)} messages from channel {channel_id}.")
            else:
                await self.scrapper_logger.debug(f"No messages fetched from channel {channel_id}.")

    async def update_or_create_message_handler(self) -> None:
        """
        Updates PyroGram's message handler. If not created, creates a new one.
        """
        if not self.channels_and_messages.keys():
            raise ValueError("No channels subscribed")

        if self.message_handler:
            await self.pyro_client.remove_handler(self.message_handler)
            self.message_handler = None

        @self.pyro_client.on_message(filters.chat(list(self.channels_and_messages.keys())))
        async def message_handler(message: Any) -> None:
            """
            Handles the incoming messages from the channels.
            """
            chat_name = self.channels_and_messages[message.chat.id][0]
            if message.text:
                if self.getting_messages_event.is_set():
                    await self.new_message_queue.put((message.chat.id, chat_name, message.text))
                else:
                    self.channels_and_messages[message.chat.id][1].append(message.text)
                await self.scrapper_logger.debug(f"Got new message from channel {message.chat.id}: {message.text}")
            else:
                await self.scrapper_logger.debug(f"Message {message.message_id} in channel {message.chat.id} is not a text message. Skipping.")

        self.message_handler = message_handler

    def __aiter__(self):
        self.getting_messages_event.set()
        self._existing_messages_iter = iter(self.channels_and_messages.items())
        self._current_channel_id = None
        self._current_message_iter = None
        return self

    async def __anext__(self):
        while self._existing_messages_iter:
            if self._current_message_iter is None:
                try:
                    self._current_channel_id, (channel_name, messages) = next(self._existing_messages_iter)
                    self._current_message_iter = iter(messages)
                    self._current_channel_name = channel_name
                except StopIteration:
                    break
            try:
                return self._current_channel_id, self._current_channel_name, next(self._current_message_iter)
            except StopIteration:
                self._current_message_iter = None

        channel_id, chat_name, msg = await self.new_message_queue.get()

        if msg is None:
            raise StopAsyncIteration
        return channel_id, chat_name, msg

    async def scrapper_start(self):
        """
        The main loop of the scrapper. It runs in a separate process and handles the incoming messages.
        """
        await self.pyro_client.start()
        await self.scrapper_logger.debug("Scrapper started.")
        self.running = True

    async def scrapper_stop(self):
        """
        Stops the scrapper.
        """
        await self.pyro_client.stop()
        await self.scrapper_logger.debug("Scrapper stopped.")
        self.running = False

