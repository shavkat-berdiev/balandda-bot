from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    bot_token: str
    main_bot_username: str = "berdiev_shavkat_bot"   # Login Widget bot for analytics.berdiev.uz
    # Front-office login bot for calendar.balandda.uz (separate Login Widget domain).
    front_bot_token: str = ""
    front_bot_username: str = ""

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

    # Owner digests (bookings + money-in + wallets; OWNER users only).
    # The evening digest goes out together with the daily report (daily_report_hour).
    owner_digest_morning_hour: int = 9
    owner_digest_morning_minute: int = 0

    # Admin
    admin_user_id: int | None = None

    # Customer messaging bridge (@balandda_bot lives in the CRM project)
    customer_bot_username: str = "balandda_bot"           # for connect deep-links
    crm_api_url: str = "https://crm.balandda.uz"          # CRM sends customer messages via @balandda_bot
    bridge_secret: str = ""                               # shared secret with the CRM (== CRM INTAKE_SECRET)
    prepayment_instructions: str = (
        "Для подтверждения брони внесите предоплату 20% в течение часа:\n"
        "💳 Карта: 8600 XXXX XXXX XXXX (ИМЯ ФАМИЛИЯ)\n"
        "После оплаты отправьте скриншот в этом чате."
    )
    # Live-editable prepayment text (balandda.uz/admin?view=rates); falls back to the default above
    prepayment_url: str = "https://www.balandda.uz/prepayment.php"

    # Billz POS (XUSH retail — api-admin.billz.ai)
    billz_api_key: str = ""          # secret_token for REST auth
    billz_sklad_api_key: str = ""    # warehouse-specific token (if different)

    # Beds24 channel manager (OTA sync: Booking.com / Airbnb / Trip.com)
    beds24_enabled: bool = False
    beds24_refresh_token: str = ""            # long-lived token (SETTINGS→API in Beds24)
    beds24_property_id: int = 340623          # "Balandda Chimgan"
    beds24_markup_percent: float = 20.0       # added on top of UZS price for OTA rates
    beds24_usd_rate: float = 0                # manual UZS/USD override; 0 = auto CBU rate
    beds24_sync_days: int = 365               # how far ahead to push availability/prices

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
