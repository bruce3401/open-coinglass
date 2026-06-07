from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from typing import Any

from playwright.async_api import Page, async_playwright

from coininfo.db import Database
from coininfo.scrapers.base import BaseScraper

# CoinGecko ID -> CoinGlass symbol mapping for detail coins
COINGLASS_SYMBOLS = {"BTC": "BTC", "ETH": "ETH", "SOL": "SOL"}


class CoinGlassScraper(BaseScraper):
    """Scrapes CoinGlass via headless browser DOM extraction.

    Pages scraped:
    1. Homepage — global stats + per-coin OI/liquidation table
    2. /FundingRate — detailed funding rates per exchange
    3. /currencies/{coin} — BTC/ETH/SOL detail (L/S ratio, liq breakdown, volumes)
    """

    def __init__(self, db: Database, interval: int = 300, proxy: str | None = None, detail_coins: list[str] | None = None) -> None:
        super().__init__(db=db, interval=interval, name="coinglass")
        self._pw = None
        self._browser = None
        self._context = None
        self._cycle = 0
        self._proxy = proxy
        self._detail_coins = detail_coins or ["BTC", "ETH", "SOL"]

    async def setup(self) -> None:
        self._pw = await async_playwright().start()
        launch_opts: dict[str, Any] = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
        }
        if self._proxy:
            launch_opts["proxy"] = {"server": self._proxy}
        self._browser = await self._pw.chromium.launch(**launch_opts)
        self._context = await self._browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        await self._context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.logger.info("coinglass_setup", headless=True, proxy=bool(self._proxy))

    async def teardown(self) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def scrape(self) -> None:
        self._cycle += 1
        ts = datetime.now(timezone.utc).isoformat()

        # 1. Homepage: global stats + OI/liquidation per coin
        try:
            await self._scrape_homepage(ts)
        except Exception as e:
            self.logger.warning("homepage_failed", error=str(e))

        await asyncio.sleep(random.uniform(2, 4))

        # 2. Funding rates page
        try:
            await self._scrape_funding_rates(ts)
        except Exception as e:
            self.logger.warning("funding_rates_failed", error=str(e))

        await asyncio.sleep(random.uniform(2, 4))

        # 3. Detail pages for BTC/ETH/SOL — also update coin_detail with CoinGlass volumes
        for coin in self._detail_coins:
            try:
                vol_data = await self._scrape_coin_detail(ts, coin)
                if vol_data:
                    await self.db.update_coin_detail_volumes(ts, coin, vol_data)
            except Exception as e:
                self.logger.warning("coin_detail_failed", coin=coin, error=str(e))
            await asyncio.sleep(random.uniform(2, 4))

        # Restart browser periodically
        if self._cycle % 30 == 0:
            self.logger.info("browser_restart", cycle=self._cycle)
            await self.teardown()
            await self.setup()

    async def _open_page(self, url: str, wait_ms: int = 6000) -> Page:
        assert self._context is not None
        page = await self._context.new_page()
        await page.goto(url, wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(wait_ms)
        return page

    # ==================================================================
    # Homepage
    # ==================================================================

    async def _scrape_homepage(self, ts: str) -> None:
        page = await self._open_page("https://www.coinglass.com")
        try:
            # Global stats
            stats = await page.evaluate(_JS_GLOBAL_STATS)
            if stats and stats.get("total_oi"):
                await self.db.insert_market_stats(ts, stats["total_oi"], stats.get("total_vol", 0), stats.get("total_liq", 0))
                self.logger.info("market_stats_stored")

            # Per-coin table
            coins = await page.evaluate(_JS_HOMEPAGE_TABLE)
            if coins:
                oi_records = [(c["symbol"], "all", c["oi"], c.get("oi_24h_pct")) for c in coins if c.get("oi")]
                liq_records = [(c["symbol"], 0, 0, c["liq_24h"]) for c in coins if c.get("liq_24h")]
                await self.db.insert_open_interest(ts, oi_records)
                await self.db.insert_liquidations(ts, liq_records)
                self.logger.info("homepage_data_stored", oi=len(oi_records), liq=len(liq_records))
        finally:
            await page.close()

    # ==================================================================
    # Funding Rates
    # ==================================================================

    async def _scrape_funding_rates(self, ts: str) -> None:
        page = await self._open_page("https://www.coinglass.com/FundingRate")
        try:
            data = await page.evaluate(_JS_FUNDING_RATES)
            if data and data.get("rates"):
                records = []
                for r in data["rates"]:
                    for ex, rate in r.get("exchange_rates", {}).items():
                        if rate is not None:
                            records.append((r["symbol"], ex, rate))
                if records:
                    await self.db.insert_funding_rates(ts, records)
                    self.logger.info("funding_rates_stored", count=len(records))
        finally:
            await page.close()

    # ==================================================================
    # Coin Detail (/currencies/BTC etc.)
    # ==================================================================

    async def _scrape_coin_detail(self, ts: str, coin: str) -> dict | None:
        page = await self._open_page(f"https://www.coinglass.com/currencies/{coin}")
        try:
            data = await page.evaluate(_JS_COIN_DETAIL)
            if not data:
                self.logger.warning("no_coin_detail", coin=coin)
                return None

            # Long/short liquidations (aggregated from exchange table)
            long_liq = data.get("long_liq_24h", 0)
            short_liq = data.get("short_liq_24h", 0)
            total_liq = long_liq + short_liq
            if total_liq > 0:
                await self.db.insert_liquidations(ts, [(coin, long_liq, short_liq, total_liq)])

            # Long/short ratios (3 types: retail, whale_account, whale_position)
            ls_records = []
            for ls in data.get("long_short", []):
                account = ls.get("type", "unknown")
                ratio = ls.get("ratio", 0)
                long_pct = ratio / (1 + ratio) if ratio > 0 else 0
                short_pct = 1 - long_pct
                ls_records.append((coin, account, ratio, long_pct, short_pct))
            if ls_records:
                await self.db.insert_long_short_ratio(ts, ls_records)

            # Per-exchange OI + liquidations from exchange table
            oi_records = []
            for ex in data.get("exchanges", []):
                if ex.get("oi"):
                    oi_records.append((coin, ex["exchange"], ex["oi"], None))
            if oi_records:
                await self.db.insert_open_interest(ts, oi_records)

            self.logger.info("coin_detail_stored", coin=coin, ls=len(ls_records), oi=len(oi_records),
                           long_liq=long_liq, short_liq=short_liq)

            return {
                "futures_vol_24h_usd": data.get("futures_vol_24h"),
                "spot_vol_24h_usd": data.get("spot_vol_24h"),
            }
        finally:
            await page.close()


# ======================================================================
# JavaScript extraction functions
# ======================================================================

_JS_GLOBAL_STATS = """() => {
    const text = document.body.innerText;
    function parseVal(label) {
        const idx = text.indexOf(label);
        if (idx < 0) return null;
        const after = text.substring(idx + label.length, idx + label.length + 80);
        const m = after.match(/\\$([0-9,.]+)/);
        if (!m) return null;
        return parseFloat(m[1].replace(/,/g, ''));
    }
    return {
        total_oi: parseVal('Open Interest'),
        total_vol: parseVal('24h Volume'),
        total_liq: parseVal('24h Liquidation'),
    };
}"""

_JS_HOMEPAGE_TABLE = """() => {
    const rows = document.querySelectorAll('tr');
    const results = [];
    let colMap = {};
    for (const row of rows) {
        const cells = row.querySelectorAll('th, td');
        const texts = Array.from(cells).map(c => c.textContent.trim());
        if (texts.includes('Symbol') && texts.includes('OI')) {
            texts.forEach((t, i) => { colMap[t] = i; });
            break;
        }
    }
    if (!colMap['Symbol']) return [];
    function parseDollar(t) {
        if (!t) return null;
        const m = t.match(/\\$([0-9,.]+)([TBMK]?)/);
        if (!m) return null;
        let v = parseFloat(m[1].replace(/,/g, ''));
        if (m[2]==='T') v*=1e12; else if (m[2]==='B') v*=1e9; else if (m[2]==='M') v*=1e6; else if (m[2]==='K') v*=1e3;
        return v;
    }
    function parsePct(t) {
        if (!t) return null;
        const m = t.match(/(-?[0-9.]+)%/);
        return m ? parseFloat(m[1]) : null;
    }
    for (const row of rows) {
        const cells = row.querySelectorAll('td');
        if (cells.length < 5) continue;
        const texts = Array.from(cells).map(c => c.textContent.trim());
        const si = colMap['Symbol'] || 2;
        const sm = (texts[si]||'').match(/^([A-Z0-9]{2,10})/);
        if (!sm) continue;
        const coin = {symbol: sm[1]};
        if (colMap['OI'] !== undefined) coin.oi = parseDollar(texts[colMap['OI']]);
        if (colMap['OI (24h%)'] !== undefined) coin.oi_24h_pct = parsePct(texts[colMap['OI (24h%)']]);
        if (colMap['Liquidation (24h)'] !== undefined) coin.liq_24h = parseDollar(texts[colMap['Liquidation (24h)']]);
        results.push(coin);
    }
    return results;
}"""

_JS_FUNDING_RATES = """() => {
    const rows = document.querySelectorAll('tr');
    const result = {exchanges: [], rates: []};
    const bodyText = document.body.innerText;
    const knownEx = ['Binance','OKX','Bybit','KuCoin','MEXC','BingX','Gate','Bitunix','Bitget','WhiteBIT','LBank'];
    const headerArea = bodyText.substring(0, bodyText.indexOf('BTC') || 500);
    const ordered = [];
    let sp = 0;
    for (let i = 0; i < 20; i++) {
        let best = null, bestIdx = Infinity;
        for (const ex of knownEx) {
            if (ordered.includes(ex)) continue;
            const idx = headerArea.indexOf(ex, sp);
            if (idx >= 0 && idx < bestIdx) { best = ex; bestIdx = idx; }
        }
        if (!best) break;
        ordered.push(best);
        sp = bestIdx + best.length;
    }
    result.exchanges = ordered.length > 0 ? ordered : knownEx.filter(e => bodyText.includes(e));
    for (const row of rows) {
        const cells = row.querySelectorAll('td');
        if (cells.length < 3) continue;
        let symbol = '', dsi = 0;
        for (let i = 0; i < Math.min(3, cells.length); i++) {
            const t = cells[i].textContent.trim().replace(/Predicted.*/, '').replace(/\\n.*/s, '').trim();
            if (/^[A-Z][A-Z0-9]{1,9}$/.test(t)) { symbol = t; dsi = i + 1; break; }
        }
        if (!symbol) continue;
        const er = {};
        let ei = 0;
        for (let i = dsi; i < cells.length && ei < result.exchanges.length; i++) {
            const m = cells[i].textContent.trim().match(/(-?[0-9]+\\.[0-9]+)%/);
            if (m) er[result.exchanges[ei]] = parseFloat(m[1]) / 100;
            ei++;
        }
        if (Object.keys(er).length > 0) result.rates.push({symbol, exchange_rates: er});
    }
    return result;
}"""

_JS_COIN_DETAIL = """() => {
    const text = document.body.innerText;
    const result = {};

    function parseDollarLabel(label) {
        const idx = text.indexOf(label);
        if (idx < 0) return null;
        const after = text.substring(idx + label.length, idx + label.length + 80);
        const m = after.match(/\\$([0-9,.]+)([TBMK]?)/);
        if (!m) return null;
        let v = parseFloat(m[1].replace(/,/g, ''));
        if (m[2]==='T') v*=1e12; else if (m[2]==='B') v*=1e9; else if (m[2]==='M') v*=1e6; else if (m[2]==='K') v*=1e3;
        return v;
    }

    function parseDollarStr(t) {
        if (!t) return null;
        const m = t.match(/\\$([0-9,.]+)([TBMK]?)/);
        if (!m) return null;
        let v = parseFloat(m[1].replace(/,/g, ''));
        if (m[2]==='T') v*=1e12; else if (m[2]==='B') v*=1e9; else if (m[2]==='M') v*=1e6; else if (m[2]==='K') v*=1e3;
        return v;
    }

    // Volumes from header stats
    result.futures_vol_24h = parseDollarLabel('Futures Vol (24h)');
    result.spot_vol_24h = parseDollarLabel('Spot Vol (24h)');

    // Long/Short Ratios from text (not table)
    // Pattern: "Long/Short Ratio(Accounts) | 2.0989"
    // Pattern: "Top Trader Long/Short (Accounts) | 2.283"
    // Pattern: "Top Trader Long/Short (Positions) | 0.9786"
    const ls = [];
    const lsPatterns = [
        {pattern: 'Long/Short Ratio(Accounts)', type: 'retail'},
        {pattern: 'Top Trader Long/Short (Accounts)', type: 'whale_account'},
        {pattern: 'Top Trader Long/Short (Positions)', type: 'whale_position'},
    ];
    for (const p of lsPatterns) {
        const idx = text.indexOf(p.pattern);
        if (idx < 0) continue;
        const after = text.substring(idx + p.pattern.length, idx + p.pattern.length + 30);
        const m = after.match(/([0-9]+\\.?[0-9]*)/);
        if (m) ls.push({type: p.type, ratio: parseFloat(m[1])});
    }
    result.long_short = ls;

    // Exchange table — header has 15 cols but data rows have 12 (sub-headers merged)
    // Data cols: 0=Rank, 1=Exchange, 2=Pair, 3=Price, 4=Price%, 5=Volume+%, 6=OI+%, 7=L/S, 8=LongLiq, 9=ShortLiq, 10=OI/Vol+%, 11=Liquidity
    const rows = document.querySelectorAll('tr');
    const exchanges = [];
    let totalLongLiq = 0, totalShortLiq = 0;
    const knownEx = ['Binance','OKX','Bybit','KuCoin','Gate','Bitget','BingX','MEXC','Bitunix','Hyperliquid','WhiteBIT','LBank','dYdX'];

    for (const row of rows) {
        const cells = row.querySelectorAll('td');
        if (cells.length < 8) continue;
        const texts = Array.from(cells).map(c => c.textContent.trim());

        const exName = texts[1];
        const exchange = knownEx.find(e => exName?.includes(e));
        if (!exchange) continue;

        const ex = {exchange};
        ex.volume = parseDollarStr(texts[5]);    // Volume (24h) + %
        ex.oi = parseDollarStr(texts[6]);         // OI + %
        ex.long_liq = parseDollarStr(texts[8]);   // Long Liq
        ex.short_liq = parseDollarStr(texts[9]);  // Short Liq

        if (ex.long_liq) totalLongLiq += ex.long_liq;
        if (ex.short_liq) totalShortLiq += ex.short_liq;

        exchanges.push(ex);
    }

    result.exchanges = exchanges;
    result.long_liq_24h = totalLongLiq;
    result.short_liq_24h = totalShortLiq;

    return result;
}"""
