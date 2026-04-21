from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Pydantic подхватывает .env только для объявленных полей; os.getenv (Yandex GPT и т.д.) — нет.
# Явная загрузка из корня пакета Verida-Backend, чтобы не зависеть от cwd при uvicorn.
_env_file = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_file)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://verida:verida@localhost:5432/verida"

    jwt_secret_key: str = Field(
        default="dev-only-change-me-min-32-characters-long!!",
        min_length=32,
        description="Секрет HS256 для access JWT; в проде задать через окружение.",
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    @property
    def database_url_sync(self) -> str:
        """URL для Alembic (синхронный драйвер psycopg3)."""
        if "+asyncpg" not in self.database_url:
            return self.database_url
        return self.database_url.replace("+asyncpg", "+psycopg", 1)


settings = Settings()
