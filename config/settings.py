from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    gemini_api_key: Optional[str] = Field(None, validation_alias="GOOGLE_API_KEY", description="API ключ для Google Gemini")
    mcp_server_url: Optional[str] = Field(None, description="URL или путь для запуска MCP сервера (NodeJS)")
    obsidian_vault_path: str = Field("test_vault", validation_alias="OBSIDIAN_VAULT_PATH", description="Путь к хранилищу Obsidian")
    orange_port: int = Field(8000, validation_alias="ORANGE_PORT", description="Порт для HTTP сервера Obsidian")


    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True
    )

def get_settings() -> Settings:
    """Загружает настройки из .env файла и переменных окружения."""
    return Settings()
