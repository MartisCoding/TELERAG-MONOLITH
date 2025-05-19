from pydantic_settings import BaseSettings

class TGConfig(BaseSettings):
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "./logs/"
    LOG_SIZE_THRESHOLD: str = "1 MB"
    LOG_AGE_THRESHOLD: str = "1 day"
    LOG_ENCODING: str = "utf-8"

    MAX_EXECUTORS: int = 10
    MIN_EXECUTORS: int = 1
    EXECUTOR_TIMEOUT: int = 60
    MAX_EXECUTOR_QUEUE_SIZE: int = 100
    MAX_MANAGER_QUEUE_SIZE: int = 100

    RAG_HOST: str = "localhost"
    RAG_PORT: int = 8080
    RAG_N_RESULT: int = 5
    SENTENCE_TRANSFORMER_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    LLM_API_KEY: str = "<KEY>"
    LLM_MODEL: str = "mistral-7b:free"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 1000

    PYRO_API_ID: str = "<ID>"
    PYRO_API_HASH: str = "<HASH>"
    PYRO_HISTORY_LIMIT: int = 100

    MONGO_USERNAME: str = "<USERNAME>"
    MONGO_PASSWORD: str = "<PASSWORD>"
    MONGO_HOST: str = "localhost"
    MONGO_PORT: int = 27017
    MONGO_DATABASE_NAME: str = "<DATABASE>"

    AIOGRAM_API_KEY: str = "<KEY>"

    class Config:
        env_file = ".env"
        case_sensitive = False



def get_config() -> TGConfig:
    stn = TGConfig()
    print(stn.__dict__)
    return stn




