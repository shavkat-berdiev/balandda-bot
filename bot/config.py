from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    bot_token: str

    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "balandda"
    db_user: str = "balandda"
    db_password: str = "change_me_in_production"

    # App
    environment: str = "development"
    log_level: str = "INFO"

    # Reports
    daily_report_hour: int = 21
    daily_report_minute: int = 0
    timezone: str = "Asia/Tashkent"

    # Admin
    admin_user_id: int = 0

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
