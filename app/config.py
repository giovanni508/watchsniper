"""Configurazione centralizzata dell'applicazione (Pydantic Settings, legge `.env`)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "sqlite+aiosqlite:///./watchsniper.db"

    # Telegram
    telegram_bot_token: str = ""

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Scraper
    scrape_interval_seconds: int = 300
    scraper_min_delay: float = 2.0
    scraper_max_delay: float = 7.0
    scraper_headless: bool = True
    # Default False: ignorare gli errori TLS è insicuro. Abilitare solo dietro
    # un proxy MITM fidato (es. proxy aziendale o ambiente sandbox).
    scraper_ignore_https_errors: bool = False
    # Resilienza: tentativi e backoff su fetch falliti, e numero massimo di
    # pagine di risultati da seguire per ogni referenza.
    scraper_max_retries: int = 3
    scraper_retry_base_delay: float = 2.0
    scraper_max_pages: int = 1

    # Analyzer
    estimated_fixed_costs: float = 300.0
    deals_min_margin_percentage: float = 10.0

    # Logging
    log_level: str = "INFO"

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()
