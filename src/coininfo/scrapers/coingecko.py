from __future__ import annotations

import math
from datetime import datetime, timezone

import aiohttp

from coininfo.db import Database
from coininfo.scrapers.base import BaseScraper

BASE_URL = "https://api.coingecko.com/api/v3"

# CoinGecko IDs for detail coins
GECKO_IDS = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}


class CoinGeckoScraper(BaseScraper):
    def __init__(
        self,
        db: Database,
        interval: int = 300,
        api_key: str | None = None,
        top_n: int = 250,
        proxy: str | None = None,
        detail_coins: list[str] | None = None,
    ) -> None:
        super().__init__(db=db, interval=interval, name="coingecko")
        self.api_key = api_key
        self.top_n = top_n
        self._proxy = proxy
        self._detail_coins = detail_coins or ["BTC", "ETH", "SOL"]
        self._session: aiohttp.ClientSession | None = None
        self._cycle = 0
        self._default_params: dict = {}

    async def setup(self) -> None:
        headers = {"Accept": "application/json"}
        self._default_params = {}
        if self.api_key:
            self._default_params["x_cg_demo_api_key"] = self.api_key
        self._session = aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=30))
        self.logger.info("coingecko_setup", has_api_key=bool(self.api_key), top_n=self.top_n, proxy=bool(self._proxy))

    async def teardown(self) -> None:
        if self._session:
            await self._session.close()

    async def scrape(self) -> None:
        self._cycle += 1
        ts = datetime.now(timezone.utc).isoformat()

        # Always: global markets
        await self._fetch_markets(ts)

        # Always: detail coins (BTC/ETH/SOL)
        await self._fetch_detail_coins(ts)

        # Every 5th cycle: trending
        if self._cycle % 5 == 0:
            await self._fetch_trending(ts)

    async def _get(self, path: str, params: dict | None = None) -> dict | list:
        assert self._session is not None
        merged = {**self._default_params, **(params or {})}
        async with self._session.get(f"{BASE_URL}{path}", params=merged, proxy=self._proxy) as resp:
            if resp.status == 429:
                self.logger.warning("rate_limited")
                raise RuntimeError("CoinGecko rate limited (429)")
            resp.raise_for_status()
            return await resp.json()

    # ------------------------------------------------------------------
    # Global markets (250 coins snapshot)
    # ------------------------------------------------------------------

    async def _fetch_markets(self, ts: str) -> None:
        per_page = 250
        pages = math.ceil(self.top_n / per_page)
        all_coins: list[dict] = []

        for page in range(1, pages + 1):
            data = await self._get("/coins/markets", {
                "vs_currency": "usd", "order": "market_cap_desc",
                "per_page": per_page, "page": page, "sparkline": "false",
            })
            for c in data:
                all_coins.append({
                    "symbol": c.get("symbol", ""),
                    "name": c.get("name", ""),
                    "price_usd": c.get("current_price") or 0,
                    "market_cap_usd": c.get("market_cap"),
                    "market_cap_rank": c.get("market_cap_rank"),
                    "volume_24h_usd": c.get("total_volume"),
                    "pct_24h": c.get("price_change_percentage_24h"),
                })

        await self.db.upsert_coin_markets(ts, all_coins)
        self.logger.info("markets_fetched", count=len(all_coins))

    # ------------------------------------------------------------------
    # Detail coins (BTC/ETH/SOL via /coins/{id})
    # ------------------------------------------------------------------

    async def _fetch_detail_coins(self, ts: str) -> None:
        details: list[dict] = []

        for coin in self._detail_coins:
            gecko_id = GECKO_IDS.get(coin)
            if not gecko_id:
                continue
            try:
                data = await self._get(f"/coins/{gecko_id}", {
                    "localization": "false", "tickers": "false",
                    "community_data": "false", "developer_data": "false",
                })
                md = data.get("market_data", {})
                details.append({
                    "symbol": coin,
                    "price_usd": md.get("current_price", {}).get("usd"),
                    "high_24h": md.get("high_24h", {}).get("usd"),
                    "low_24h": md.get("low_24h", {}).get("usd"),
                    "pct_1h": md.get("price_change_percentage_1h_in_currency", {}).get("usd"),
                    "pct_24h": md.get("price_change_percentage_24h"),
                    "pct_7d": md.get("price_change_percentage_7d"),
                    "pct_14d": md.get("price_change_percentage_14d"),
                    "pct_30d": md.get("price_change_percentage_30d"),
                    "market_cap_usd": md.get("market_cap", {}).get("usd"),
                    "market_cap_rank": md.get("market_cap_rank"),
                    "volume_24h_usd": md.get("total_volume", {}).get("usd"),
                    "circulating_supply": md.get("circulating_supply"),
                    "max_supply": md.get("max_supply"),
                    "sentiment_up_pct": data.get("sentiment_votes_up_percentage"),
                    "sentiment_down_pct": data.get("sentiment_votes_down_percentage"),
                })
            except Exception as e:
                self.logger.warning("detail_fetch_error", coin=coin, error=str(e))

        if details:
            await self.db.insert_coin_detail(ts, details)
            self.logger.info("detail_coins_fetched", count=len(details))

    # ------------------------------------------------------------------
    # Trending
    # ------------------------------------------------------------------

    async def _fetch_trending(self, ts: str) -> None:
        data = await self._get("/search/trending")
        coins = []
        for i, item in enumerate(data.get("coins", [])):
            c = item.get("item", {})
            coins.append({
                "symbol": c.get("symbol", ""),
                "name": c.get("name", ""),
                "market_cap_rank": c.get("market_cap_rank"),
                "score": i,
            })
        await self.db.upsert_trending(ts, coins)
        self.logger.info("trending_fetched", count=len(coins))
