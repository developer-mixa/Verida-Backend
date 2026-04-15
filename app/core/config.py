from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://verida:verida@localhost:5432/verida"

    @property
    def database_url_sync(self) -> str:
        """URL для Alembic (синхронный драйвер psycopg3)."""
        if "+asyncpg" not in self.database_url:
            return self.database_url
        return self.database_url.replace("+asyncpg", "+psycopg", 1)


settings = Settings()
