from pydantic_settings import BaseSettings, SettingsConfigDict #type:ignore
from pathlib import Path

CURRENT_FOLDER = Path(__file__).parent.absolute()
ENV_FILE_PATH = CURRENT_FOLDER / ".env"

class Config(BaseSettings):
    
    PORT: int
    GEMINI_API_KEY: str
    POSTGRES_DB_URI: str
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_DEFAULT_REGION: str
    AWS_BUCKET_NAME: str

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

config = Config()