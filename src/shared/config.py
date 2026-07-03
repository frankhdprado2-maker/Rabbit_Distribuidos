from functools import lru_cache
import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


class Settings:
    def __init__(self) -> None:
        self.app_env = os.getenv("APP_ENV", "development")
        self.sqlite_db_path = os.getenv("SQLITE_DB_PATH", "data/fisi_ordenes.db")
        self.rabbitmq_host = os.getenv("RABBITMQ_HOST", "localhost")
        self.rabbitmq_port = int(os.getenv("RABBITMQ_PORT", "5672"))
        self.rabbitmq_user = os.getenv("RABBITMQ_USER", "guest")
        self.rabbitmq_password = os.getenv("RABBITMQ_PASSWORD", "guest")
        self.rabbitmq_vhost = os.getenv("RABBITMQ_VHOST", "/")
        self.rabbitmq_exchange = os.getenv("RABBITMQ_EXCHANGE", "fisi.ordenes.exchange")
        self.rabbitmq_dlx = os.getenv("RABBITMQ_DLX", "fisi.ordenes.dlx")

    @property
    def db_path(self) -> Path:
        path = Path(self.sqlite_db_path)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
