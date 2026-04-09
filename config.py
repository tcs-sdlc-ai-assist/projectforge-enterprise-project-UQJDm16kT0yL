from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SECRET_KEY: str = "change-me-in-production-use-a-real-secret-key"
    DATABASE_URL: str = "sqlite+aiosqlite:///./projectforge.db"
    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = "admin123"
    TOKEN_EXPIRY_SECONDS: int = 3600


settings = Settings()