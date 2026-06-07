from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

from coininfo.log import get_logger
from coininfo.models import (
    CoinDetail,
    CoinMarket,
    FundingRate,
    LiquidationRecord,
    LongShortRecord,
    MarketStats,
    OpenInterestRecord,
    ScrapeHealth,
    TrendingCoin,
)

logger = get_logger("db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS funding_rates (
    ts       TEXT NOT NULL,
    symbol   TEXT NOT NULL,
    exchange TEXT NOT NULL,
    rate     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fr_ts ON funding_rates(ts DESC);
CREATE INDEX IF NOT EXISTS idx_fr_sym_ts ON funding_rates(symbol, ts DESC);

CREATE TABLE IF NOT EXISTS open_interest (
    ts             TEXT NOT NULL,
    symbol         TEXT NOT NULL,
    exchange       TEXT NOT NULL DEFAULT 'all',
    oi_usd         REAL NOT NULL,
    change_24h_pct REAL
);
CREATE INDEX IF NOT EXISTS idx_oi_ts ON open_interest(ts DESC);
CREATE INDEX IF NOT EXISTS idx_oi_sym_ts ON open_interest(symbol, ts DESC);

CREATE TABLE IF NOT EXISTS liquidations (
    ts            TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    long_liq_usd  REAL NOT NULL DEFAULT 0,
    short_liq_usd REAL NOT NULL DEFAULT 0,
    total_liq_usd REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_liq_ts ON liquidations(ts DESC);
CREATE INDEX IF NOT EXISTS idx_liq_sym_ts ON liquidations(symbol, ts DESC);

CREATE TABLE IF NOT EXISTS long_short_ratio (
    ts        TEXT NOT NULL,
    symbol    TEXT NOT NULL,
    account   TEXT NOT NULL,
    ratio     REAL NOT NULL,
    long_pct  REAL NOT NULL,
    short_pct REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lsr_ts ON long_short_ratio(ts DESC);
CREATE INDEX IF NOT EXISTS idx_lsr_sym_ts ON long_short_ratio(symbol, ts DESC);

CREATE TABLE IF NOT EXISTS market_stats (
    ts                   TEXT NOT NULL,
    total_oi_usd         REAL NOT NULL,
    total_volume_24h_usd REAL NOT NULL,
    total_liq_24h_usd    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ms_ts ON market_stats(ts DESC);

CREATE TABLE IF NOT EXISTS coin_detail (
    ts                  TEXT NOT NULL,
    symbol              TEXT NOT NULL,
    price_usd           REAL,
    high_24h            REAL,
    low_24h             REAL,
    pct_1h              REAL,
    pct_24h             REAL,
    pct_7d              REAL,
    pct_14d             REAL,
    pct_30d             REAL,
    market_cap_usd      REAL,
    market_cap_rank     INTEGER,
    volume_24h_usd      REAL,
    futures_vol_24h_usd REAL,
    spot_vol_24h_usd    REAL,
    circulating_supply  REAL,
    max_supply          REAL,
    sentiment_up_pct    REAL,
    sentiment_down_pct  REAL
);
CREATE INDEX IF NOT EXISTS idx_cd_ts ON coin_detail(ts DESC);
CREATE INDEX IF NOT EXISTS idx_cd_sym_ts ON coin_detail(symbol, ts DESC);

CREATE TABLE IF NOT EXISTS coin_markets (
    symbol           TEXT NOT NULL,
    name             TEXT NOT NULL,
    price_usd        REAL NOT NULL,
    market_cap_usd   REAL,
    market_cap_rank  INTEGER,
    volume_24h_usd   REAL,
    pct_24h          REAL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cm_rank ON coin_markets(market_cap_rank ASC);

CREATE TABLE IF NOT EXISTS trending_coins (
    symbol          TEXT NOT NULL,
    name            TEXT NOT NULL,
    market_cap_rank INTEGER,
    score           INTEGER NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scrape_meta (
    source             TEXT PRIMARY KEY,
    last_success       TEXT,
    last_error         TEXT,
    error_count        INTEGER DEFAULT 0,
    consecutive_errors INTEGER DEFAULT 0
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cutoff(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self._path))
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()
        logger.info("db_initialized", path=str(self._path))

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None
        return self._conn

    # ===================================================================
    # Funding Rates
    # ===================================================================

    async def insert_funding_rates(self, ts: str, rates: list[tuple[str, str, float]]) -> None:
        """rates: list of (symbol, exchange, rate)"""
        if not rates:
            return
        await self.conn.executemany(
            "INSERT INTO funding_rates (ts, symbol, exchange, rate) VALUES (?, ?, ?, ?)",
            [(ts, s, e, r) for s, e, r in rates],
        )
        await self.conn.commit()

    async def get_funding_rates(self, symbol: str | None = None, hours: float | None = None) -> list[FundingRate]:
        if hours:
            q = "SELECT ts, symbol, exchange, rate FROM funding_rates WHERE ts >= ?"
            params: list = [_cutoff(hours)]
            if symbol:
                q += " AND UPPER(symbol) = UPPER(?)"
                params.append(symbol)
            q += " ORDER BY ts DESC, symbol, exchange"
        else:
            # Latest batch only
            q = "SELECT ts, symbol, exchange, rate FROM funding_rates WHERE ts = (SELECT MAX(ts) FROM funding_rates)"
            params = []
            if symbol:
                q = "SELECT ts, symbol, exchange, rate FROM funding_rates WHERE ts = (SELECT MAX(ts) FROM funding_rates) AND UPPER(symbol) = UPPER(?)"
                params = [symbol]
            q += " ORDER BY symbol, exchange"
        rows = await self.conn.execute_fetchall(q, params)
        return [FundingRate(ts=r[0], symbol=r[1], exchange=r[2], rate=r[3]) for r in rows]

    # ===================================================================
    # Open Interest
    # ===================================================================

    async def insert_open_interest(self, ts: str, records: list[tuple[str, str, float, float | None]]) -> None:
        """records: list of (symbol, exchange, oi_usd, change_24h_pct)"""
        if not records:
            return
        await self.conn.executemany(
            "INSERT INTO open_interest (ts, symbol, exchange, oi_usd, change_24h_pct) VALUES (?, ?, ?, ?, ?)",
            [(ts, s, e, o, c) for s, e, o, c in records],
        )
        await self.conn.commit()

    async def get_open_interest(self, symbol: str | None = None, hours: float | None = None) -> list[OpenInterestRecord]:
        if hours:
            q = "SELECT ts, symbol, exchange, oi_usd, change_24h_pct FROM open_interest WHERE ts >= ?"
            params: list = [_cutoff(hours)]
            if symbol:
                q += " AND UPPER(symbol) = UPPER(?)"
                params.append(symbol)
            q += " ORDER BY ts DESC, oi_usd DESC"
        else:
            q = "SELECT ts, symbol, exchange, oi_usd, change_24h_pct FROM open_interest WHERE ts = (SELECT MAX(ts) FROM open_interest)"
            params = []
            if symbol:
                q = "SELECT ts, symbol, exchange, oi_usd, change_24h_pct FROM open_interest WHERE ts = (SELECT MAX(ts) FROM open_interest) AND UPPER(symbol) = UPPER(?)"
                params = [symbol]
            q += " ORDER BY oi_usd DESC"
        rows = await self.conn.execute_fetchall(q, params)
        return [OpenInterestRecord(ts=r[0], symbol=r[1], exchange=r[2], oi_usd=r[3], change_24h_pct=r[4]) for r in rows]

    # ===================================================================
    # Liquidations
    # ===================================================================

    async def insert_liquidations(self, ts: str, records: list[tuple[str, float, float, float]]) -> None:
        """records: list of (symbol, long_liq, short_liq, total_liq)"""
        if not records:
            return
        await self.conn.executemany(
            "INSERT INTO liquidations (ts, symbol, long_liq_usd, short_liq_usd, total_liq_usd) VALUES (?, ?, ?, ?, ?)",
            [(ts, s, l, sh, t) for s, l, sh, t in records],
        )
        await self.conn.commit()

    async def get_liquidations(self, symbol: str | None = None, hours: float | None = None) -> list[LiquidationRecord]:
        if hours:
            q = "SELECT ts, symbol, long_liq_usd, short_liq_usd, total_liq_usd FROM liquidations WHERE ts >= ?"
            params: list = [_cutoff(hours)]
            if symbol:
                q += " AND UPPER(symbol) = UPPER(?)"
                params.append(symbol)
            q += " ORDER BY ts DESC, total_liq_usd DESC"
        else:
            q = "SELECT ts, symbol, long_liq_usd, short_liq_usd, total_liq_usd FROM liquidations WHERE ts = (SELECT MAX(ts) FROM liquidations)"
            params = []
            if symbol:
                q = "SELECT ts, symbol, long_liq_usd, short_liq_usd, total_liq_usd FROM liquidations WHERE ts = (SELECT MAX(ts) FROM liquidations) AND UPPER(symbol) = UPPER(?)"
                params = [symbol]
            q += " ORDER BY total_liq_usd DESC"
        rows = await self.conn.execute_fetchall(q, params)
        return [LiquidationRecord(ts=r[0], symbol=r[1], long_liq_usd=r[2], short_liq_usd=r[3], total_liq_usd=r[4]) for r in rows]

    # ===================================================================
    # Long/Short Ratio
    # ===================================================================

    async def insert_long_short_ratio(self, ts: str, records: list[tuple[str, str, float, float, float]]) -> None:
        """records: list of (symbol, account, ratio, long_pct, short_pct)"""
        if not records:
            return
        await self.conn.executemany(
            "INSERT INTO long_short_ratio (ts, symbol, account, ratio, long_pct, short_pct) VALUES (?, ?, ?, ?, ?, ?)",
            [(ts, s, a, r, lp, sp) for s, a, r, lp, sp in records],
        )
        await self.conn.commit()

    async def get_long_short_ratio(self, symbol: str | None = None, hours: float | None = None) -> list[LongShortRecord]:
        if hours:
            q = "SELECT ts, symbol, account, ratio, long_pct, short_pct FROM long_short_ratio WHERE ts >= ?"
            params: list = [_cutoff(hours)]
            if symbol:
                q += " AND UPPER(symbol) = UPPER(?)"
                params.append(symbol)
            q += " ORDER BY ts DESC, symbol, account"
        else:
            q = "SELECT ts, symbol, account, ratio, long_pct, short_pct FROM long_short_ratio WHERE ts = (SELECT MAX(ts) FROM long_short_ratio)"
            params = []
            if symbol:
                q = "SELECT ts, symbol, account, ratio, long_pct, short_pct FROM long_short_ratio WHERE ts = (SELECT MAX(ts) FROM long_short_ratio) AND UPPER(symbol) = UPPER(?)"
                params = [symbol]
            q += " ORDER BY symbol, account"
        rows = await self.conn.execute_fetchall(q, params)
        return [LongShortRecord(ts=r[0], symbol=r[1], account=r[2], ratio=r[3], long_pct=r[4], short_pct=r[5]) for r in rows]

    # ===================================================================
    # Market Stats
    # ===================================================================

    async def insert_market_stats(self, ts: str, total_oi: float, total_vol: float, total_liq: float) -> None:
        await self.conn.execute(
            "INSERT INTO market_stats (ts, total_oi_usd, total_volume_24h_usd, total_liq_24h_usd) VALUES (?, ?, ?, ?)",
            (ts, total_oi, total_vol, total_liq),
        )
        await self.conn.commit()

    async def get_market_stats(self, hours: float | None = None) -> list[MarketStats]:
        if hours:
            q = "SELECT ts, total_oi_usd, total_volume_24h_usd, total_liq_24h_usd FROM market_stats WHERE ts >= ? ORDER BY ts DESC"
            params: list = [_cutoff(hours)]
        else:
            q = "SELECT ts, total_oi_usd, total_volume_24h_usd, total_liq_24h_usd FROM market_stats ORDER BY ts DESC LIMIT 1"
            params = []
        rows = await self.conn.execute_fetchall(q, params)
        return [MarketStats(ts=r[0], total_oi_usd=r[1], total_volume_24h_usd=r[2], total_liq_24h_usd=r[3]) for r in rows]

    # ===================================================================
    # Coin Detail (BTC/ETH/SOL)
    # ===================================================================

    async def insert_coin_detail(self, ts: str, details: list[dict]) -> None:
        if not details:
            return
        await self.conn.executemany(
            "INSERT INTO coin_detail (ts, symbol, price_usd, high_24h, low_24h, "
            "pct_1h, pct_24h, pct_7d, pct_14d, pct_30d, "
            "market_cap_usd, market_cap_rank, volume_24h_usd, futures_vol_24h_usd, spot_vol_24h_usd, "
            "circulating_supply, max_supply, sentiment_up_pct, sentiment_down_pct) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    ts, d["symbol"], d.get("price_usd"), d.get("high_24h"), d.get("low_24h"),
                    d.get("pct_1h"), d.get("pct_24h"), d.get("pct_7d"), d.get("pct_14d"), d.get("pct_30d"),
                    d.get("market_cap_usd"), d.get("market_cap_rank"), d.get("volume_24h_usd"),
                    d.get("futures_vol_24h_usd"), d.get("spot_vol_24h_usd"),
                    d.get("circulating_supply"), d.get("max_supply"),
                    d.get("sentiment_up_pct"), d.get("sentiment_down_pct"),
                )
                for d in details
            ],
        )
        await self.conn.commit()

    async def update_coin_detail_volumes(self, ts: str, symbol: str, vol_data: dict) -> None:
        """Update futures/spot volumes from CoinGlass into the coin_detail row inserted by CoinGecko."""
        await self.conn.execute(
            "UPDATE coin_detail SET futures_vol_24h_usd = ?, spot_vol_24h_usd = ? "
            "WHERE ts = ? AND UPPER(symbol) = UPPER(?)",
            (vol_data.get("futures_vol_24h_usd"), vol_data.get("spot_vol_24h_usd"), ts, symbol),
        )
        await self.conn.commit()

    async def get_coin_detail(self, symbol: str, hours: float | None = None) -> list[CoinDetail]:
        if hours:
            q = "SELECT * FROM coin_detail WHERE UPPER(symbol) = UPPER(?) AND ts >= ? ORDER BY ts DESC"
            params: list = [symbol, _cutoff(hours)]
        else:
            q = "SELECT * FROM coin_detail WHERE UPPER(symbol) = UPPER(?) AND ts = (SELECT MAX(ts) FROM coin_detail WHERE UPPER(symbol) = UPPER(?)) ORDER BY ts DESC"
            params = [symbol, symbol]
        rows = await self.conn.execute_fetchall(q, params)
        return [
            CoinDetail(
                ts=r[0], symbol=r[1], price_usd=r[2], high_24h=r[3], low_24h=r[4],
                pct_1h=r[5], pct_24h=r[6], pct_7d=r[7], pct_14d=r[8], pct_30d=r[9],
                market_cap_usd=r[10], market_cap_rank=r[11], volume_24h_usd=r[12],
                futures_vol_24h_usd=r[13], spot_vol_24h_usd=r[14],
                circulating_supply=r[15], max_supply=r[16],
                sentiment_up_pct=r[17], sentiment_down_pct=r[18],
            )
            for r in rows
        ]

    # ===================================================================
    # Coin Markets (snapshot)
    # ===================================================================

    async def upsert_coin_markets(self, ts: str, coins: list[dict]) -> None:
        if not coins:
            return
        await self.conn.execute("DELETE FROM coin_markets")
        await self.conn.executemany(
            "INSERT INTO coin_markets (symbol, name, price_usd, market_cap_usd, market_cap_rank, volume_24h_usd, pct_24h, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(c["symbol"], c["name"], c["price_usd"], c.get("market_cap_usd"), c.get("market_cap_rank"), c.get("volume_24h_usd"), c.get("pct_24h"), ts) for c in coins],
        )
        await self.conn.commit()

    async def get_coin_markets(self, limit: int = 100, symbol: str | None = None) -> list[CoinMarket]:
        q = "SELECT symbol, name, price_usd, market_cap_usd, market_cap_rank, volume_24h_usd, pct_24h FROM coin_markets"
        params: list = []
        if symbol:
            q += " WHERE UPPER(symbol) = UPPER(?)"
            params.append(symbol)
        q += " ORDER BY market_cap_rank ASC LIMIT ?"
        params.append(limit)
        rows = await self.conn.execute_fetchall(q, params)
        return [CoinMarket(symbol=r[0], name=r[1], price_usd=r[2], market_cap_usd=r[3], market_cap_rank=r[4], volume_24h_usd=r[5], pct_24h=r[6]) for r in rows]

    # ===================================================================
    # Trending (snapshot)
    # ===================================================================

    async def upsert_trending(self, ts: str, coins: list[dict]) -> None:
        if not coins:
            return
        await self.conn.execute("DELETE FROM trending_coins")
        await self.conn.executemany(
            "INSERT INTO trending_coins (symbol, name, market_cap_rank, score, updated_at) VALUES (?, ?, ?, ?, ?)",
            [(c["symbol"], c["name"], c.get("market_cap_rank"), c["score"], ts) for c in coins],
        )
        await self.conn.commit()

    async def get_trending(self) -> list[TrendingCoin]:
        rows = await self.conn.execute_fetchall("SELECT symbol, name, market_cap_rank, score FROM trending_coins ORDER BY score ASC")
        return [TrendingCoin(symbol=r[0], name=r[1], market_cap_rank=r[2], score=r[3]) for r in rows]

    # ===================================================================
    # Scrape Meta
    # ===================================================================

    async def update_scrape_meta(self, source: str, success: bool, error: str | None = None) -> None:
        now = _now()
        if success:
            await self.conn.execute(
                "INSERT INTO scrape_meta (source, last_success, consecutive_errors) VALUES (?, ?, 0) "
                "ON CONFLICT(source) DO UPDATE SET last_success=?, consecutive_errors=0",
                (source, now, now),
            )
        else:
            await self.conn.execute(
                "INSERT INTO scrape_meta (source, last_error, error_count, consecutive_errors) VALUES (?, ?, 1, 1) "
                "ON CONFLICT(source) DO UPDATE SET last_error=?, error_count=error_count+1, consecutive_errors=consecutive_errors+1",
                (source, error, error),
            )
        await self.conn.commit()

    async def get_scrape_health(self) -> list[ScrapeHealth]:
        rows = await self.conn.execute_fetchall("SELECT source, last_success, last_error, consecutive_errors FROM scrape_meta")
        return [ScrapeHealth(source=r[0], last_success=r[1], last_error=r[2], consecutive_errors=r[3]) for r in rows]

    # ===================================================================
    # Cleanup
    # ===================================================================

    async def cleanup(self, retention_days: int = 30) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        tables = ["funding_rates", "open_interest", "liquidations", "long_short_ratio", "market_stats", "coin_detail"]
        total = 0
        for table in tables:
            cursor = await self.conn.execute(f"DELETE FROM {table} WHERE ts < ?", (cutoff,))
            total += cursor.rowcount
        await self.conn.commit()
        if total > 0:
            logger.info("cleanup_done", deleted=total, retention_days=retention_days)
