from pydantic_settings import BaseSettings, SettingsConfigDict #type: ignore
from pathlib import Path

CURRENT_FOLDER = Path(__file__).parent.absolute()
ENV_FILE_PATH = CURRENT_FOLDER / ".env"

class Config(BaseSettings):
    VERSION: str
    AUTHENTICATION_SECRET_KEY: str
    AUTHENTICATION_ALGORITHM: str
    AUTHENTICATION_ACCESS_TOKEN_EXPIRE_MINUTES: int
    POSTGRES_DB_URI: str

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

config = Config()