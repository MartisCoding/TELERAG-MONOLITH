import source.Core as Cr
from source.Database.DBHelper import DataBaseHelper
from source.TgUI.BotApp import BotApp
from source.DevUI.webInterface import WebInterface
from source.ChromaАndRAG.ChromaClient import RagClient
from source.TelegramMessageScrapper.Base import Scrapper
class TeleragService:
    """
    The TeleragService class is responsible for managing the Telegram message scrapper and the RAG client.
    It handles the initialization, updating, and querying of channels and messages.
    """

    def __init__(self, settings):
        self.scheduler = Cr.TaskScheduling.TaskScheduler(
            max_workers=settings.MAX_WORKERS,
            max_async_workers=settings.MAX_ASYNC_WORKERS,
        )
        self.RagClient = RagClient(
            host=settings.RAG_HOST,
            port=settings.RAG_PORT,
            n_result=settings.N_RESULT,
            model=settings.SENTENCE_TRANSFORMER_MODEL,
            mistral_api_key=settings.MISTRAL_API_KEY,
            mistral_model=settings.MISTRAL_MODEL,
        )
        self.Scrapper = Scrapper(
            api_id=settings.TELEGRAM_API_ID,
            api_hash=settings.TELEGRAM_API_HASH,
        )
        self.DataBaseHelper =