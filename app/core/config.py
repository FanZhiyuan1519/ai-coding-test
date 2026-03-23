import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ai-coding"
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    AI_ENABLED: bool = True
    AI_MODEL_URL: str = "http://10.3.75.113:1002/v1/chat/completions"
    AI_MODEL_PROVIDER: str = "openai"
    AI_MODEL_ID: str = "qwen3.5-35b-a3b-4bit"
    AI_API_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
