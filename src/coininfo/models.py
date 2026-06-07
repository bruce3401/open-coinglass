from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class DataResponse(BaseModel, Generic[T]):
    data: T
    source: str


# ---------------------------------------------------------------------------
# CoinGlass
# ---------------------------------------------------------------------------

class FundingRate(BaseModel):
    ts: str
    symbol: str
    exchange: str
    rate: float


class OpenInterestRecord(BaseModel):
    ts: str
    symbol: str
    exchange: str
    oi_usd: float
    change_24h_pct: float | None = None


class LiquidationRecord(BaseModel):
    ts: str
    symbol: str
    long_liq_usd: float
    short_liq_usd: float
    total_liq_usd: float


class LongShortRecord(BaseModel):
    ts: str
    symbol: str
    account: str  # retail / whale_account / whale_position
    ratio: float
    long_pct: float
    short_pct: float


class MarketStats(BaseModel):
    ts: str
    total_oi_usd: float
    total_volume_24h_usd: float
    total_liq_24h_usd: float


# ---------------------------------------------------------------------------
# Coin detail (CoinGecko + CoinGlass merged, BTC/ETH/SOL)
# ---------------------------------------------------------------------------

class CoinDetail(BaseModel):
    ts: str
    symbol: str
    price_usd: float | None = None
    high_24h: float | None = None
    low_24h: float | None = None
    pct_1h: float | None = None
    pct_24h: float | None = None
    pct_7d: float | None = None
    pct_14d: float | None = None
    pct_30d: float | None = None
    market_cap_usd: float | None = None
    market_cap_rank: int | None = None
    volume_24h_usd: float | None = None
    futures_vol_24h_usd: float | None = None
    spot_vol_24h_usd: float | None = None
    circulating_supply: float | None = None
    max_supply: float | None = None
    sentiment_up_pct: float | None = None
    sentiment_down_pct: float | None = None


# ---------------------------------------------------------------------------
# CoinGecko global
# ---------------------------------------------------------------------------

class CoinMarket(BaseModel):
    symbol: str
    name: str
    price_usd: float
    market_cap_usd: float | None = None
    market_cap_rank: int | None = None
    volume_24h_usd: float | None = None
    pct_24h: float | None = None


class TrendingCoin(BaseModel):
    symbol: str
    name: str
    market_cap_rank: int | None = None
    score: int


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class ScrapeHealth(BaseModel):
    source: str
    last_success: str | None = None
    last_error: str | None = None
    consecutive_errors: int = 0
