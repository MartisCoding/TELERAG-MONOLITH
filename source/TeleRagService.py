import asyncio

import source.Core as Cr
from source.Database.DBHelper import DataBaseHelper
from source.TgUI.BotApp import BotApp
from source.DevUI.webInterface import WebInterface
from source.ChromaАndRAG.ChromaClient import RagClient
from source.TelegramMessageScrapper.Base import Scrapper
class TeleRagService:
    """
    The TeleragService class is responsible for managing the Telegram message scrapper and the RAG client.
    It handles the initialization, updating, and querying of channels and messages.
    """

    def __init__(self, settings):
        self.scheduler = Cr.TaskScheduling.TaskScheduler(
            max_workers=settings.Core.MAX_WORKERS,
            max_async_workers=settings.Core.MAX_ASYNC_WORKERS,
        )
        self.profiler = Cr.Profiling.Profiler(
            interval=settings.Core.PROFILER_INTERVAL,
            snapshots=settings.Core.PROFILER_SNAPSHOTS,
        )
        self.RagClient = RagClient(
            host=settings.Rag.RAG_HOST,
            port=settings.Rag.RAG_PORT,
            n_result=settings.Rag.N_RESULT,
            model=settings.Rag.SENTENCE_TRANSFORMER_MODEL,
            mistral_api_key=settings.Rag.MISTRAL_API_KEY,
            mistral_model=settings.Rag.MISTRAL_MODEL,
        )
        self.Scrapper = Scrapper(
            api_id=settings.Pyrogram.PYRO_TELEGRAM_API_ID,
            api_hash=settings.Pyrogram.PYRO_TELEGRAM_API_HASH,
            history_limit=settings.Pyrogram.PYRO_TELEGRAM_HISTORY_LIMIT,
        )
        asyncio.create_task(self.__create_db())
        self.BotApp = BotApp(
            token=settings.Aiogram.TELEGRAM_TOKEN,
        )
        self.WebInterface = WebInterface(
            secret=settings.Web.SECRET,
            host=settings.Web.HOST,
            port=settings.Web.PORT,
        )
        Cr.DependencyInjection.finalize_dependencies()
        self.stop_event = asyncio.Event()
        self.register_stop_signal_handler()

    async def start(self):
        self.RagClient.start_rag()
        await self.Scrapper.scrapper_start()
        await self.BotApp.start()

    async def idle(self):
        await self.stop_event.wait()
        await self.Scrapper.scrapper_stop()
        await self.RagClient.stop()
        await self.WebInterface.stop()
        self.stop_event.clear()
        # log

    def __stop_signal_handler(self):
        self.stop_event.set()

    def register_stop_signal_handler(self):
        """
        Register a signal handler for stopping the service.
        """
        import signal
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGTERM, self.__stop_signal_handler)
        loop.add_signal_handler(signal.SIGINT, self.__stop_signal_handler)

    async def __create_db(self, settings):
        self.DataBaseHelper = await DataBaseHelper.create(
            uri=self.construct_url(settings),
            db_name=settings.Mongo.DB_NAME,
        )

    @staticmethod
    def construct_url(settings):
        """
        Construct the MongoDB URI from the settings.
        """
        return f"mongodb://{settings.Mongo.USER}:{settings.Mongo.PASSWORD}@{settings.Mongo.HOST}:{settings.Mongo.PORT}/"
