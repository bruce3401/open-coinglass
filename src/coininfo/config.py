from __future__ import annotations

from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = {"env_file": str(_PROJECT_ROOT / ".env"), "extra": "ignore"}

    # Service
    host: str = "0.0.0.0"
    port: int = 8100
    log_level: str = "INFO"
    log_file: str = "logs/coininfo.log"
    db_path: str = "data/coininfo.db"

    # Proxy (optional HTTP/HTTPS proxy for all scrapers, e.g. http://proxy.example.com:3128)
    http_proxy: str | None = None

    # Scrape intervals (seconds)
    coinglass_scrape_interval: int = 300
    coingecko_scrape_interval: int = 300

    # CoinGecko
    coingecko_api_key: SecretStr | None = None
    coingecko_top_n: int = 250

    # API gate: if set, /api/* requires header `X-API-Key: <value>`
    api_key: SecretStr | None = None

    # Detail coins (CoinGlass + CoinGecko detailed data)
    detail_coins: str = "BTC,ETH,SOL"

    # Retention
    retention_days: int = 30

    @property
    def db_abs_path(self) -> Path:
        p = Path(self.db_path)
        if not p.is_absolute():
            p = _PROJECT_ROOT / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


def load_settings() -> Settings:
    return Settings()
