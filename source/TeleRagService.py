from source.Database.MongoHelper import MongoDBHelper
from source.TgUI.AiogramIntegration import AiogramBot
from source.TelegramMessageScrapper.Crawler import TeleRagCrawler
from source.ChromaАndRAG.ChromaDBHelper import ChromaDBHelper
from source.ChromaАndRAG.llmGateway import LLMGateway
from source.Logging import LoggerRegistry, GateWayStrategy
from source.ResponseProcessing import ExecutorManager
from source.DynamicConfigurationLoading import TGConfig
class TeleRagService:
    def __init__(self, settings: TGConfig):
        self.registry = LoggerRegistry(
            level=settings.LOG_LEVEL,
            gateway_strategy=GateWayStrategy(
                directory=settings.LOG_DIRECTORY,
                ext=".log",
                size_threshold=settings.LOG_SIZE_THRESHOLD,
                age_threshold=settings.LOG_AGE_THRESHOLD,
                encoding=settings.LOG_ENCODING,
            )
        )
        self.executor = ExecutorManager(
            maximum_executors=settings.MAX_EXECUTORS,
            minimum_executors=settings.MIN_EXECUTORS,
            executor_timeout=settings.EXECUTOR_TIMEOUT,
            max_queue_size=settings.MAX_EXECUTOR_QUEUE_SIZE,
            max_self_queue_size=settings.MAX_MANAGER_QUEUE_SIZE
        )
        self.llm_gateway = LLMGateway(
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS
        )
        self.chroma_db = ChromaDBHelper(
            model=settings.SENTENCE_TRANSFORMER_MODEL,
            host=settings.RAG_HOST,
            port=settings.RAG_PORT,
            n_result=settings.RAG_N_RESULT,
            max_chunk_size_in_sentences=5,
            max_cache=1000,
            time_to_live=60,
            llm_gateway=self.llm_gateway
        )
        self.crawler = TeleRagCrawler(
            api_id=settings.PYRO_API_ID,
            api_hash=settings.PYRO_API_HASH,
            history_limit=settings.PYRO_HISTORY_LIMIT,
            chroma=self.chroma_db
        )
        self.mongo_helper = MongoDBHelper.create(
            crawler=self.crawler,
            uri=f"mongodb://{settings.MONGO_USERNAME}:{settings.MONGO_PASSWORD}@{settings.MONGO_HOST}:{settings.MONGO_PORT}/",
            db_name=settings.MONGO_DATABASE_NAME,
        )
        self.bot = AiogramBot(
            token=settings.AIOGRAM_TOKEN,
            db=self.mongo_helper,
        )

    async def start(self):
        """
        Starts the TeleRagService.
        """
        await self.crawler.start()
        await self.bot.start()

    async def stop(self):
        await self.crawler.stop()