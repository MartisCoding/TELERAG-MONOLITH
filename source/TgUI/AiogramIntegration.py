import re

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
from source.MiddleWareResponseModels import RetrievalAugmentedResponse
from source.ResponseProcessing import push_task
from source.TgUI.States import AddSourceStates, ProcessingResponseStates
from source.Database.MongoHelper import MongoDBHelper
from source.Database.exceptions import *
from source.Logging import get_logger


# noinspection SpellCheckingInspection
# 19 may started implementing logging.
class AiogramBot:

    def __init__(self, token: str, db: MongoDBHelper):
        self.token = token
        self.storage = MemoryStorage()
        self.bot = Bot(token=token, default=DefaultBotProperties(
            parse_mode="HTML",
        ))
        self.dispatcher = Dispatcher(storage=self.storage)
        self.router = Router()
        self.dispatcher.include_router(self.router)
        self._handlers()
        self.aiogramm_logger = get_logger("AiogramBot", "network")
        self.db = db


    def _handlers(self):
        self.router.message.register(self._handle_start, F.text == "/start")
        self.router.message.register(self._handle_end, F.text == "/end")
        self.router.message.register(self._handle_license, F.text == "/license")
        self.router.message.register(self._handle_help, F.text == "/help")
        self.router.message.register(self._handle_add, F.text == "/add")
        self.router.message.register(self._handle_remove, F.text == "/remove")
        self.router.message.register(self._handle_source, AddSourceStates.waiting_for_source)
        self.router.message.register(self._handle_cancel, F.text == "Отмена🔴")
        self.router.message.register(self._handle_message)
        self.router.callback_query.register(self._handle_callback)


    async def _handle_start(self, message: Message, state: FSMContext):
        if state.get_state() == ProcessingResponseStates.waiting_for_processing:
            await message.answer(
                "Ваше сообщение обрабатывается, я не могу выполнять никакие другие действия.\n"
                "Пожалуйста, подождите."
            )
            return
        await self.bot.set_my_commands(
            [
                BotCommand(command="/start", description="Начать"),
                BotCommand(command="/help", description="Помощь"),
                BotCommand(command="/add", description="Добавить новый источник"),
                BotCommand(command="/remove", description="Удалить источник"),
                BotCommand(command="/end", description="Завершить сессию"),
                BotCommand(command="/license", description="Получить информацию о лицензии"),
            ]
        )
        self.aiogramm_logger.info(f"User {message.from_user.first_name} started the bot.")

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
    async def _handle_license(message: Message, state: FSMContext):
        if state.get_state() == ProcessingResponseStates.waiting_for_processing:
            await message.answer(
                "Ваше сообщение обрабатывается, я не могу выполнять никакие другие действия.\n"
                "Пожалуйста, подождите."
            )
            return
        await message.answer(
            "Проект находится под лицензией AGPL v3:\n"
            "https://www.gnu.org/licenses/agpl-3.0.txt"
        )

    @staticmethod
    async def _handle_help(message: Message, state: FSMContext):
        if state.get_state() == ProcessingResponseStates.waiting_for_processing:
            await message.answer(
                "Ваше сообщение обрабатывается, я не могу выполнять никакие другие действия.\n"
                "Пожалуйста, подождите."
            )
            return

        await message.answer(
            "Доступные команды:\n\n"
            "/add — введите команду, после чего вас попросят ввести название источника, введите ссылку вида https://t.me/your_channel\n"
            "/remove — для удаления источника, выберите источник из списка доступных источников, используя инлайн-кнопки.\n"
            "/end — чтобы удалить свой аккаунт.\n\n"
            "Для получения информации о лицензии используйте /licence."
        )

    @staticmethod
    async def _handle_add(
            message: Message, state: FSMContext
    ):
        if state.get_state() == ProcessingResponseStates.waiting_for_processing:
            await message.answer(
                "Ваше сообщение обрабатывается, я не могу выполнять никакие другие действия.\n"
                "Пожалуйста, подождите."
            )
            return
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
    async def _handle_cancel( message: Message, state: FSMContext):
        await state.clear()
        await message.answer(
            "Добавление источника отменено.",
            reply_markup=ReplyKeyboardRemove()
        )

    async def _handle_source(self, message: Message, state: FSMContext):
        if message.text == "Отмена🔴":
            await self._handle_cancel(message, state)
            return

        source_link = message.text
        # Here we should validate the source link and add it to the database
        # If the link is valid, we can proceed, if not, we should inform the user
        if source_link.startswith("@"):
            channel_name = source_link[1:]
        else:
            channel_name = re.search(r"(?:https?://)?t\.me/([a-zA-Z0-9_]+)", source_link)

        self.aiogramm_logger.info(f"User {message.from_user.first_name} trying to add source {source_link}.")
        if not channel_name:
            channel_name = source_link
        # Here we validate if the name is indeed a channel
        try:
            chat = await self.bot.get_chat(f"@{channel_name.group(1)}")
        except Exception:
            self.aiogramm_logger.error(f"User {message.from_user.first_name} failed to add source {source_link}.")
            await message.answer(
                "Не удалось получить информацию о канале. Возможно вы ввели ссылку на приватный канал.\n"
                "К сожалению, сервис работает только с публичными каналами из соображений конфиденциальности.\n"
                "Если же канал публичный, проверьте правильность ссылки или имени и введите её снова.\n"
            )
            return
        if chat.type != "channel" or chat.type != "supergroup":
            self.aiogramm_logger.error(f"User {message.from_user.first_name} added wrong type of source {source_link}.")
            await message.answer(
                "Ссылка не ведет на канал. Сервис, не может работать с группами или пользователями напрямую. \n"
                "Пожалуйста, введите ссылку на публичный канал вида https://t.me/your_channel или нажмите 'Отмена🔴'."
            )
            return
        # First validate if user exists in database, if not, create a new user
        try:
            await self.db.get_user(message.from_user.id)
        except UserNotFound:
            self.aiogramm_logger.info(f"User does {message.from_user.first_name} not exist in database. Creating new user.")
            await self.db.create_user(
                user_id=message.from_user.id,
                name=message.from_user.first_name
            )
            await message.answer(
                "Судя по всему вы новый пользователь. Добро пожаловать!\n"
            )

        # Now we validate if the channel already exists in the database, if not, create a new entry
        try:
            await self.db.get_channel(chat.id)
        except ChannelNotFound:
            self.aiogramm_logger.info(f"Channel {chat.title} does not exist in database. Creating new channel.")
            try:
                await self.db.create_channel(chat.id, channel_name)
            except CannotEndTransaction as e:
                self.aiogramm_logger.error(f"Could not create channel {chat.title} in database. {e}")
                await message.answer(
                    "К сожалению, не удалось добавить канал в базу данных. Пожалуйста, свяжитесь с техподдержкой.\n"
                )
                await self._handle_cancel(message, state)
                return


        # Now we add the channel to the user
        try:
            await self.db.add_for_user(message.from_user.id, chat.id)
        except ChannelsAlreadyPresentInUser:
            # if channel already present in user model we inform them
            await self.aiogramm_logger.warning(f"User {message.from_user.first_name} tried to add channel {chat.title} that already exists in his database record.")
            await message.answer(
                f"К сожалению, канал уже добавлен в ваш список источников.\n"
            )
            await self._handle_cancel(message, state)
            return
        except UserNotFound:
            # This should not happen, but just in case we inform the user
            # At least I hope so, because we already created a user above,
            # and this exception would mean that this is something with the database
            self.aiogramm_logger.critical(f"User cannot be found in database after creating it. {message.from_user.first_name}")
            await message.answer(
                "К сожалению, обновить каналы не удалось из-за внутренней ошибки. Пожалуйста, свяжитесь с техподдержкой."
            )
            await self._handle_cancel(message, state)
            return
        # Now we inform the user that the channel was added successfully
        self.aiogramm_logger.info(f"User {message.from_user.first_name} added channel {chat.title} to his database record.")
        await message.answer(
            "Канал успешно добавлен в ваш список источников.\n"
            "Если вы хотите удалить источник, используйте команду /remove.\n"
            "Если хотите добавить еще один источник, используйте команду /add."
        )
        # Now we clear the state
        await state.clear()

    async def _hande_get(self, message: Message, state: FSMContext):
        # Handle get to present the list of sources user has saved
        # First, we validate if user exists in database.
        if state.get_state() == ProcessingResponseStates.waiting_for_processing:
            await message.answer(
                "Ваше сообщение обрабатывается, я не могу выполнять никакие другие действия.\n"
                "Пожалуйста, подождите."
            )
            return

        self.aiogramm_logger.info(f"User {message.from_user.first_name} trying to get sources.")
        try:
            user = await self.db.get_user(message.from_user.id)
        except UserNotFound:
            self.aiogramm_logger.info(f"User {message.from_user.first_name} not exist in database.")
            await message.answer(
                "К сожалению, вы не зарегистрированы в системе. Добавьте хотя бы один источник, чтобы продолжить.\n"
            )
            return

        # Now we get the list of channels from the database
        channels = user.channels
        if not channels:
            # This one is strange condition, because, well, we create user only when they add a channel,
            # but just in case we inform the user. If, when testing, this happens, we should investigate
            self.aiogramm_logger.critical(f"User {message.from_user.first_name} has no channels in database. Must be a bug.")
            await message.answer(
                "У вас нет источников. Пожалуйста, добавьте источник с помощью команды /add."
            )
            return
        list_channels = list(channels.items())
        # Now we present the list of channels to the user
        await self._return_pages_from_get(message, list_channels, page=1)

    @staticmethod
    async def _return_pages_from_get(message: Message, channels: list, page: int):
        items_per_page = 5
        start = (page - 1) * items_per_page
        end = start + items_per_page
        if end >= len(channels):
            end = len(channels) - 1
        current_channels = channels[start:end]
        keyboard = []
        # Firstly, we must build the inline keyboard for navigation
        navigation_buttons = [[]]
        if page > 1:
            navigation_buttons[0].append(InlineKeyboardButton(
                text="<--", callback_data=f":get:page:{page - 1}:channels:{channels}"))
        if end < len(channels) - 1:
            navigation_buttons[0].append(InlineKeyboardButton(
                text="-->", callback_data=f":get:page:{page + 1}:channels:{channels}"))
        if navigation_buttons:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=navigation_buttons
            )
        try:
            await message.answer(
                f"Ваш список источников:\n {'\n'.join([channel[1] for channel in current_channels])}\n\n",
                reply_markup=keyboard
            )
        except Exception:
            await message.delete()
            await message.answer(
                f"Ваш список источников:\n {'\n'.join([channel[1] for channel in current_channels])}\n\n",
                reply_markup=keyboard
            )


    async def _handle_get_for_removal(self, user_id: int):
        # Here we get the list of channels from the database
        try:
            user = await self.db.get_user(user_id)
        except UserNotFound:
            return None
        # Now we get the list of channels from the database
        channels = user.channels
        if not channels:
            # This one is strange condition, because, well, we create user only when they add a channel,
            return None
        channels_list = list(channels.items())
        return channels_list

    async def _handle_remove(self, message: Message, state: FSMContext):
        # Handle remove to present the list of sources user has saved
        if state.get_state() == ProcessingResponseStates.waiting_for_processing:
            await message.answer(
                "Ваше сообщение обрабатывается, я не могу выполнять никакие другие действия.\n"
                "Пожалуйста, подождите."
            )
            return
        channels = await self._handle_get_for_removal(message.from_user.id)
        if not channels:
            await message.answer(
                "У вас нет источников для удаления. Пожалуйста, добавьте источник с помощью команды /add."
            )
            return
        await self._return_pages(message, channels, page=1)

    @staticmethod
    async def _return_pages(message: Message, channels: list, page: int):
        items_per_page = 5
        start = (items_per_page * (page - 1))
        end = start + items_per_page
        if end >= len(channels):
            end = len(channels) - 1
        current_channels = channels[start:end]
        inline_keyboard = [
            [
                InlineKeyboardButton(
                    text=channel[1],
                    callback_data=f"from_user:{message.from_user.id}:remove:{channel}"
                )
            ]
            for channel in current_channels
        ]
        navigation_buttons = []
        if page > 1:
            navigation_buttons.append(InlineKeyboardButton(
                text="<--", callback_data=f"page:{page - 1}:channels:{channels}"))
        if end < len(channels) - 1:
            navigation_buttons.append(InlineKeyboardButton(
                text="-->", callback_data=f"page:{page + 1}:channels:{channels}"))
        if navigation_buttons:
            inline_keyboard.append(navigation_buttons)

        markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
        try:
            await message.answer(
                "Выберите источник для удаления:",
                reply_markup=markup
            )
        except Exception:
            await message.delete()
            await message.answer(
                "Выберите канал для удаления:",
                reply_markup=markup
            )

    async def _handle_callback(self, callback: CallbackQuery):
        data = callback.data
        if data.startswith("from_user:"):
            _, user_id, action, channel_id = data.split(":")
            if action == "remove":
                channel = eval(channel_id)
                try:
                    await self.db.remove_for_user(callback.message.from_user.id, channel[0])
                    await callback.message.answer(
                        "Канал успешно удален из вашего списка источников.\n"
                    )
                except UserNotFound:
                    # This should not happen, but just in case we inform the user
                    await callback.message.answer(
                        "К сожалению, обновить каналы не удалось из-за внутренней ошибки. Пожалуйста, свяжитесь с техподдержкой."
                    )
                except ChannelsNotPresentInUser:
                    # Same applies here, though this is more likely to happen
                    await callback.message.answer(
                        "К сожалению, канал не найден в вашем списке источников. Возможно вы уже удалили его.\n"
                    )
        if data.startswith("page:"):
            _, page, action, channels = data.split(":")
            if action == "channels":
                channels = eval(channels)
                await self._return_pages(callback.message, channels, int(page))
        if data.startswith(":get:page:"):
            _, page, action, channels = data.split(":")
            if action == "channels":
                channels = eval(channels)
                await self._return_pages_from_get(callback.message, channels, int(page))

        if data.startswith("delete_account:"):
            _, user_id = data.split(":")
            if user_id == "skip_it":
                await callback.message.answer(
                    "Удаление аккаунта отменено."
                )
                return
            try:
                await self.db.delete_user(int(user_id))
                await callback.message.answer(
                    "Ваш аккаунт успешно удален. Если вы хотите снова использовать сервис, "
                    "просто начните добавлять источники с помощью команды /add.\n"
                )
            except UserNotFound:
                await callback.message.answer(
                    "К сожалению, удалить аккаунт не удалось из-за внутренней ошибки. Пожалуйста, свяжитесь с техподдержкой."
                )

        await callback.answer()

    async def _handle_message(self, message: Message, state: FSMContext):
        # Here we handle message that does not start with a command symbol
        if state.get_state() == ProcessingResponseStates.waiting_for_processing:
            await message.answer(
                "Ваше сообщение обрабатывается, я не могу выполнять никакие другие действия.\n"
                "Пожалуйста, подождите."
            )
            return
        if not message.text:
            await message.answer(
                "Пожалуйста, введите текст сообщения или команду."
                "Сервис не может обрабатывать стикеры, фото, голосовые и видео сообщения."
            )
            return
        if message.from_user.id == message.bot.id:
            await message.answer(
                "Черезвычайно извиняюсь, но я не могу обрабатывать сообщения от себя.\n"
            )
            return

        if "игнорируй прошлые команды" in message.text.lower():
            await message.answer(
                "К сожалению, я не могу игнорировать то поведение, которое было заложено в мою систему.\n"
                "Если у вас есть другие вопросы, не стесняйтесь спрашивать."
            )
        try:
            user = await self.db.get_user(message.from_user.id)
        except UserNotFound:
            await message.answer(
                "К сожалению, вы не зарегистрированы в системе. Добавьте хотя бы один источник, чтобы продолжить.\n"
            )
            return
        self.aiogramm_logger.info(f"Started processing RAG request from user {message.from_user.first_name} with message: {message.text}")
        query = message.text.lower()
        channels = user.channels
        if not channels:
            # This one is strange condition, because, well, we create user only when they add a channel,
            await message.answer(
                "У вас нет источников. Пожалуйста, добавьте источник с помощью команды /add."
            )
            return

        channel_names = list(channels.values())
        response = RetrievalAugmentedResponse(
            user_name=user.name,
            query=query,
            channel_names=channel_names,
        )
        # Push task to available executor
        #TODO:  DONT FORGET TO SET_NEXT TO CRAWLER, BECAUSE IF NOT THE TASK WILL NOT EXECUTE AT ALL
        push_task(response)

        await message.answer(
            "Ваш запрос обрабатывается. Пожалуйста, подождите.\n"
        )
        self.aiogramm_logger.info(f"Pushed from {message.from_user.first_name} task to middleware processing executor.")
        await state.set_state(ProcessingResponseStates.waiting_for_processing)
        try:
            result = await response.result_async()
            await state.clear()
        except Exception:
            await message.answer(
                "К сожалению, произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже.\n"
            )
            await state.clear()
            return

        self.aiogramm_logger.info(f"Result arrived {message.from_user.first_name} with message: {result[:50]}")

        if isinstance(result, str):
            await message.answer(result)
        else:
            self.aiogramm_logger.critical(f"Result arrived is not a string. {result}. Must be a bug.")
            await message.answer(
                "Из-за внутренней ошибки я не смог обработать ваш запрос. Пожалуйста, попробуйте позже.\n"
            )


    async def _handle_end(self, message: Message):
        # Here we ask for assurance before deleting the account
        self.aiogramm_logger.info(f"User {message.from_user.first_name} trying to delete account.")
        await message.answer(
            "Вы уверены, что хотите удалить свой аккаунт?\n"
            "Это действие необратимо и приведет к удалению всех ваших источников.\n"
            "Пожалуйста, подтвердите, нажав 'Да' или 'Нет'.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Да",
                            callback_data=f"delete_account:{message.from_user.id}"
                        ),
                        InlineKeyboardButton(
                            text="Нет",
                            callback_data=f"delete_account:skip_it:"
                        )
                    ]
                ]
            )
        )


    async def start(self):
        self.aiogramm_logger.info(f"Starting Aiogram bot.")
        await self.dispatcher.start_polling()
