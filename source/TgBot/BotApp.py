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

from source.TgBot.States import AddSourceStates
from source.Config import settings


class BotApp:
    def __init__(self):
        self.bot = Bot(
            token=settings.BOT_TOKEN,
            default=DefaultBotProperties(
                parse_mode="HTML",
            )
        )
        self.dispatcher = Dispatcher(storage=MemoryStorage())
        self.router = Router()
        self.dispatcher.include_router(self.router)
        self.__include_handlers()

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

    @staticmethod
    async def __end_handler(message: Message):
        await message.answer(
            "Вы успешно вышли из сервиса. Все данные будут удалены.",
            reply_markup=ReplyKeyboardRemove()
        )
        # TODO: удалить пользователя из БД

    async def __add_command_handler(
        self, message: Message, state: FSMContext
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

    async def __cancel_handler(self, message: Message, state: FSMContext):
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

        # TODO: сохранить источник

        await message.answer(
            f"Источник \"{source_link}\" добавлен!",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()

    async def __get_channels(self):

        # TODO: Реализовать получение списка каналов из базы данных

        return [
            {"id": 101, "name": "Канал 1"},
            {"id": 102, "name": "Канал 2"},
            {"id": 103, "name": "Канал 3"},
            {"id": 104, "name": "Канал 4"},
            {"id": 105, "name": "Канал 5"},
            {"id": 106, "name": "Канал 6"},
            {"id": 107, "name": "Канал 7"},
            {"id": 108, "name": "Канал 8"},
        ]

    async def __remove_command_handler(self, message: Message):
        channels = await self.__get_channels()
        await self.__send_paginated_channels(message, channels, page=1)

    async def __send_paginated_channels(
        self,
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
                    callback_data=f"rm:{channel['id']}"
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
        if callback_data.startswith("rm:"):
            channel_id = int(callback_data.split(":")[1])

            # TODO: обработать удаление канала с указанным channel_id

            await callback_query.message.edit_text(
                f"Канал с ID {channel_id} будет удалён."
            )
        elif callback_data.startswith("page:"):
            page = int(callback_data.split(":")[1])
            channels = await self.__get_channels()
            await self.__send_paginated_channels(
                callback_query.message,
                channels,
                page
            )
        await callback_query.answer()

    @staticmethod
    async def __message_handler(message: Message):
        if not message.text:
            await message.answer(
                "Пожалуйста, отправьте текстовое сообщение."
                " Стикеры, голосовые и другие типы"
                " сообщений не поддерживаются."
            )
            return

        # TODO: !!! Добавить обработку текста сообщения,
        # но только если пользователь зарегистрирован в БД

        await message.answer(
            "Сообщение получено! Ожидайте ответа RAG."
        )

    async def start(self):
        await self.dispatcher.start_polling(self.bot)
