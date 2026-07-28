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
    # Extra Telegram IDs (comma-separated) that receive the owner digest and may
    # use /svodka without the OWNER role. 548813671 = Azizov.
    owner_digest_extra_ids: str = "548813671"

    # Admin
    admin_user_id: int | None = None

    # SPA bot (@balandda_spa_bot) — notifications to masters / SPA admin / owner.
    # Feature is fully disabled while spa_bot_token is empty.
    spa_bot_token: str = ""
    spa_admin_telegram_id: int = 0     # single SPA administrator (DM recipient)
    spa_digest_hour: int = 9           # daily schedule digest (Asia/Tashkent)
    spa_digest_minute: int = 0

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

    # iikoServer (RMS) — restaurant revenue reports (NOT iikoCloud)
    iiko_server_url: str = ""        # e.g. https://balandda.iiko.it
    iiko_server_login: str = ""
    iiko_server_password: str = ""   # plain; sha1-hashed before sending
    # Daily iiko CASH revenue is auto-credited to this wallet (restaurant manager).
    # 1016986741 = ILYOS KHUDOYBERGENOV. Set to 0 to disable the sync.
    iiko_cash_wallet_id: int = 1016986741

    # Card monitoring — reads CardXabar (UZCARD) messages via a read-only
    # Telethon userbot session of the owner's personal account.
    # Feature is fully disabled while telethon_session is empty.
    telethon_api_id: int = 0            # from my.telegram.org
    telethon_api_hash: str = ""
    telethon_session: str = ""          # StringSession (create with scripts/telethon_login.py)
    cardxabar_chat: str = "CardXabar"   # dialog title, @username, or numeric chat id
    # last4:BUSINESS pairs; business is BALANDDA or XUSH
    card_map: str = "4042:BALANDDA,8044:XUSH"
    card_recon_hour: int = 21           # daily card reconciliation post time
    card_recon_minute: int = 15

    @property
    def card_business_map(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for pair in self.card_map.split(","):
            pair = pair.strip()
            if ":" in pair:
                last4, biz = pair.split(":", 1)
                out[last4.strip()] = biz.strip().upper()
        return out

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
