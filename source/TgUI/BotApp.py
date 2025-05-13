from typing import Optional

from aiogram.client.default import DefaultBotProperties
from aiogram import Bot, Dispatcher, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BotCommand,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

from source.TgUI.States import AddSourceStates
from source.Core import Logger
from source.Database.DBHelper import DataBaseHelper
from source.ChromaАndRAG.ChromaClient import RagClient
import re, asyncio
telegram_ui_logger = Logger("TelegramUI", "network.log")


class BotApp:
    def __init__(self, token: str,db_helper: DataBaseHelper, rag: RagClient):
        self.bot = Bot(
            token=token,
            default=DefaultBotProperties(
                parse_mode="HTML",
            )
        )
        self.dispatcher = Dispatcher(storage=MemoryStorage())
        self.router = Router()
        self.dispatcher.include_router(self.router)
        self.__include_handlers()

        self.DataBaseHelper = db_helper
        self.RagClient = rag

        self.request_queueue = asyncio.Queue()
        self.response_queue = asyncio.Queue()

        self._request_task: Optional[asyncio.Task] = None
        self._response_task: Optional[asyncio.Task] = None

    def __include_handlers(self):
        # --- Хэндлеры для сообщений ---
        self.router.message.register(self.__start_handler, F.text == "/start")
        self.router.message.register(
            self.__licence_handler, F.text == "/licence"
        )
        self.router.message.register(self.__end_handler, F.text == "/end")
        self.router.message.register(
            self.__add_command_handler, F.text == "/add"
        )
        self.router.message.register(
            self.__remove_command_handler, F.text == "/remove"
        )
        self.router.message.register(self.__get_channels, F.text == "/get_channels")
        self.router.message.register(
            self.__handle_source, AddSourceStates.waiting_for_source
        )
        self.router.message.register(
            self.__cancel_handler, F.text == "Отмена🔴"
        )
        self.router.message.register(self.__message_handler)  # Хендлер RAG

        # --- Хэндлеры для инлайн-кнопок, коллбэки ---
        self.router.callback_query.register(self.__inline_button_handler)

    async def __start_handler(self, message: Message):
        await telegram_ui_logger.info(f"User {message.from_user.id} started the bot.")

        await self.bot.set_my_commands([
            BotCommand(command="/start", description="Начать работу с ботом"),
            BotCommand(command="/add", description="Добавить источник"),
            BotCommand(command="/remove", description="Удалить источник"),
            BotCommand(command="/end", description="Удалить аккаунт"),
            BotCommand(command="/licence", description="Информация о лицензии")
        ])

        await message.answer(
            f"Добро пожаловать, {message.from_user.first_name}!\n\n"
            "<u>Доступные команды:</u>\n\n"
            "/add — для добавления источника,\n"
            "/remove — для удаления \n"
            "/end — чтобы удалить свой аккаунт.\n\n"
            "Для получения информации о лицензии используйте /licence.",
            reply_markup=ReplyKeyboardRemove()
        )

    @staticmethod
    async def __licence_handler(message: Message):
        await message.answer(
            "Проект находится под лицензией AGPL v3:\n"
            "https://www.gnu.org/licenses/agpl-3.0.txt"
        )


    async def __end_handler(self, message: Message):
        await message.answer(
            "Вы успешно вышли из сервиса. Все данные будут удалены.",
            reply_markup=ReplyKeyboardRemove()
        )
        await self.DataBaseHelper.delete_user(message.from_user.id)

    @staticmethod
    async def __add_command_handler(
        message: Message, state: FSMContext
    ):
        cancel_button = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена🔴")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.answer(
            "Введите ссылку на источник или нажмите 'Отмена🔴':",
            reply_markup=cancel_button
        )
        await state.set_state(AddSourceStates.waiting_for_source)

    @staticmethod
    async def __cancel_handler( message: Message, state: FSMContext):
        await state.clear()
        await message.answer(
            "Добавление источника отменено.",
            reply_markup=ReplyKeyboardRemove()
        )

    async def __handle_source(self, message: Message, state: FSMContext):
        if message.text == "Отмена🔴":
            await self.__cancel_handler(message, state)
            return

        source_link = message.text

        # Get channel id from the link
        channel_name = re.search(r"(?:https?://)?t\.me/([a-zA-Z0-9_]+)", source_link)
        if not channel_name:
            await message.answer(
                "Некорректная ссылка на источник. Пожалуйста, попробуйте снова."
            )
            await self.__cancel_handler(message, state)
            return

        channel_chat = await self.bot.get_chat(f"@{channel_name.group(1)}")
        if not channel_chat:
            await message.answer(
                "Не удалось получить ID канала. Пожалуйста, проверьте ссылку и попробуйте снова."
            )
            await self.__cancel_handler(message, state)
            return
        channel_id = channel_chat.id
        try:
            await self.DataBaseHelper.get_user(message.from_user.id)
        except ValueError:
            await self.DataBaseHelper.create_user(
                message.from_user.id,
                message.from_user.first_name
            )

        try:
            await self.DataBaseHelper.update_user_channels(
                message.from_user.id,
                add=[channel_id]
            )
        except ValueError:
            try:
                await self.DataBaseHelper.create_channel(channel_id, channel_chat.first_name)
                await self.DataBaseHelper.update_user_channels(
                    message.from_user.id,
                    add=[channel_id]
                )
            except ValueError:
                await message.answer(
                    "Канал уже добавлен в источники. Возможно вы уже добавляли его ранее."
                )
                await self.__cancel_handler(message, state)
                return

        await message.answer(
            f"Источник \"{source_link}\" добавлен!",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()

    async def __get_channels(self, message: Message):
        try:
            user = await self.DataBaseHelper.get_user(message.from_user.id)
        except ValueError:
            await message.answer(
                "Вы не зарегистрированы в системе. Добавьте хотя бы один источник, чтобы получить доступ к этой функции."
            )
            return None


        user_channels = user.channels
        channel_names = []
        for channel in user_channels:
            chat = await self.bot.get_chat(channel)
            if chat:
                channel_names.append(f"id: {channel}, Имя: {chat.first_name}")
            else:
                channel_names.append(f"id: {channel}, Имя: Неизвестный канал")
        await message.answer(
            "Ваши источники:\n" + "\n".join(channel_names),
            reply_markup=ReplyKeyboardRemove()
        )
        return None

    async def __get_channels_internal(self, user_id: int):
        try:
            user = await self.DataBaseHelper.get_user(user_id)
        except ValueError:
            return None

        user_channels = user.channels
        channel_names = []
        for channel in user_channels:
            chat = await self.bot.get_chat(channel)
            if chat:
                channel_names.append({"id": channel, "name": chat.first_name})
            else:
                channel_names.append({"id": channel, "name": "Неизвестный канал"})

        return channel_names


    async def __remove_command_handler(self, message: Message):
        channels = await self.__get_channels_internal(message.from_user.id)
        if not channels:
            await message.answer(
                "У вас нет добавленных источников. Пожалуйста, добавьте хотя бы один источник."
            )
            return
        await self.__send_paginated_channels(message, channels, page=1)

    @staticmethod
    async def __send_paginated_channels(
        message: Message,
        channels,
        page: int
    ):
        items_per_page = 5
        start = (page - 1) * items_per_page
        end = start + items_per_page
        current_page_channels = channels[start:end]

        inline_keyboard = [
            [
                InlineKeyboardButton(
                    text=channel["name"],
                    callback_data=f"usr:{message.from_user.id} rm:{channel['id']}"
                )
            ]
            for channel in current_page_channels
        ]

        navigation_buttons = []
        if page > 1:
            navigation_buttons.append(InlineKeyboardButton(
                text="<<<", callback_data=f"page:{page - 1}"))
        if end < len(channels):
            navigation_buttons.append(InlineKeyboardButton(
                text=">>>", callback_data=f"page:{page + 1}"))
        if navigation_buttons:
            inline_keyboard.append(navigation_buttons)

        markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

        try:
            await message.edit_text(
                "Выберите канал для удаления:",
                reply_markup=markup
            )
        except Exception:
            await message.delete()
            await message.answer(
                "Выберите канал для удаления:",
                reply_markup=markup
            )

    async def __inline_button_handler(self, callback_query: CallbackQuery):
        callback_data = callback_query.data
        if callback_data.startswith("usr:"):
            usr_str, channel_str = callback_data.split(" ")
            user_id = int(usr_str.split(":")[1])
            channel_id = int(channel_str.split(":")[1])
            try:
                await self.DataBaseHelper.update_user_channels(
                    user_id,
                    remove=[channel_id]
                )
                await callback_query.message.edit_text(
                    f"Канал с ID {channel_id} будет удалён."
                )
            except ValueError:
                await callback_query.message.edit_text(
                    f"Канал с ID {channel_id} не найден."
                )
        elif callback_data.startswith("page:"):
            page = int(callback_data.split(":")[1])
            channels = await self.__get_channels_internal(user_id=callback_query.from_user.id)
            await self.__send_paginated_channels(
                callback_query.message,
                channels,
                page
            )
        await callback_query.answer()


    async def __message_handler(self, message: Message):
        if not message.text:
            await message.answer(
                "Пожалуйста, отправьте текстовое сообщение."
                " Стикеры, голосовые и другие типы"
                " сообщений не поддерживаются."
            )
            return
        if message.from_user.id == self.bot.id:
            await message.answer(
                "Черезвычайно извиняюсь, но я не могу обрабатывать сообщения от себя."
            )
            return

        try:
            user = await self.DataBaseHelper.get_user(message.from_user.id)
        except ValueError:
            await telegram_ui_logger.error("Could not get user from DB.")
            await message.answer(
                "Вы не зарегистрированы в системе. Пожалуйста, добавьте источник, чтобы получить доступ к этой функции."
            )
            return

        user_channels: list[int] = user.channels
        if not user_channels:
            await telegram_ui_logger.error("User has no channels. Or there is something wrong with DB.")
            await message.answer(
                "У вас нет добавленных источников. Пожалуйста, добавьте хотя бы один источник."
            )
            return


        # TODO: !!! Добавить обработку текста сообщения,
        # но только если пользователь зарегистрирован в БД
        await self.request_queueue.put((message.from_user.id, message.text, user_channels))

        await message.answer(
            "Сообщение получено! Ожидайте ответа RAG."
        )

    async def __request_loop(self):
        while True:
            user_id, request, channel_ids = await self.request_queueue.get()
            await telegram_ui_logger.info(f"Started processing RAG request for {user_id} with request: {request}.")
            await self.RagClient.query(user_id, request, channel_ids)

    async def __response_loop(self):
        while True:
            user_id, response = await self.RagClient.rag_response_queue.get()
            await telegram_ui_logger.info(f"Got response from RAG for {user_id}")
            try:
                await self.bot.send_message(user_id, response)
            except Exception as e:
                await telegram_ui_logger.error(f"Failed to send message to {user_id}: {e}")






    async def start(self):
        await self.dispatcher.start_polling(self.bot)
        self._request_task = asyncio.create_task(self.__request_loop())
        self._response_task = asyncio.create_task(self.__response_loop())

    async def stop(self):
        if self._request_task:
            self._request_task.cancel()
            try:
                await self._request_task
            except asyncio.CancelledError:
                pass

        if self._response_task:
            self._response_task.cancel()
            try:
                await self._response_task
            except asyncio.CancelledError:
                pass
        await self.bot.session.close()