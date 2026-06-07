# open-coinglass

> Self-hosted crypto **derivatives data aggregator**. It collects funding rates,
> open interest, liquidations, long/short ratios and market stats from
> [CoinGlass](https://www.coinglass.com), enriches them with spot/market data from
> the [CoinGecko](https://www.coingecko.com) public API, stores everything in a
> local SQLite database, and serves it back through a small REST API and a
> built-in dashboard.

English | [简体中文](./README.zh-CN.md)

---

## ⚠️ Disclaimer — read this first

- This project is provided for **personal, educational and research purposes only**.
- It is **not affiliated with, endorsed by, or connected to CoinGlass or CoinGecko**
  in any way. "CoinGlass" and "CoinGecko" are trademarks of their respective owners.
- The CoinGlass collector works by **rendering public web pages in a headless browser
  and reading the DOM** (CoinGlass does not expose a free public API for this data).
  Scraping may be against a site's Terms of Service. **You are responsible for how you
  use this software.** Check and respect the ToS / `robots.txt` of any site you point
  it at, and keep request rates reasonable.
- The software is provided **"AS IS", without warranty of any kind** (see [LICENSE](./LICENSE)).
- **Maintenance:** this is a best-effort, lightly-maintained project. DOM scrapers are
  inherently fragile — when CoinGlass changes their page markup, the CoinGlass
  collectors may break until the selectors are updated. The CoinGecko side uses the
  official public API and is much more stable.

---

## Features

- **CoinGlass metrics** (via headless-browser DOM extraction)
  - Funding rates per exchange
  - Open interest (global + per coin + per exchange)
  - Liquidations (long / short, 24h)
  - Long/short ratios (retail accounts, top-trader accounts, top-trader positions)
  - Global market stats (total OI, 24h volume, 24h liquidations)
- **CoinGecko metrics** (via the official public API)
  - Top-N market snapshot (price, market cap, rank, 24h volume, 24h change)
  - Trending coins
  - In-depth detail for a configurable set of coins (default `BTC,ETH,SOL`):
    price, highs/lows, % change over 1h–30d, supply, sentiment
- **Historical storage** in SQLite with automatic retention/cleanup
- **REST API** (FastAPI) with optional `X-API-Key` gating
- **Built-in dashboard** (single static HTML page, Chart.js) for quick visualization
- **Docker / docker-compose** deployment, plus optional HTTP proxy support

## Architecture

```
                +-------------------+        +-------------------+
   CoinGlass    |  CoinGlassScraper |        | CoinGeckoScraper  |   CoinGecko
   (web pages)  |  (Playwright DOM) |        |   (REST/aiohttp)  |   (public API)
       │        +---------┬---------+        +---------┬---------+        │
       └──────────────────┘                            └─────────────────┘
                          │                            │
                          ▼                            ▼
                    +-----------------------------------------+
                    |          SQLite (aiosqlite)             |
                    |   funding_rates / open_interest /       |
                    |   liquidations / long_short_ratio /     |
                    |   market_stats / coin_detail /          |
                    |   coin_markets / trending_coins         |
                    +--------------------┬--------------------+
                                         │
                                         ▼
                    +-----------------------------------------+
                    |        FastAPI app (uvicorn)            |
                    |   /api/coinglass/*   /api/coingecko/*   |
                    |   /health            /  (dashboard)     |
                    +-----------------------------------------+
```

Each collector runs as an independent asyncio loop on its own interval. A third loop
periodically deletes rows older than `RETENTION_DAYS`. See [docs/API.md](./docs/API.md)
for the full endpoint reference.

## Requirements

- Python **3.11+**
- [`uv`](https://github.com/astral-sh/uv) (recommended) — or any pip-based workflow
- Chromium (installed automatically via `playwright install chromium`)
- Optional: Docker / docker-compose

## Quick start (local, with uv)

```bash
git clone https://github.com/bruce3401/open-coinglass.git
cd open-coinglass

# 1. Configure (all values are optional; defaults are sensible)
cp .env.example .env

# 2. Install dependencies + Chromium
uv sync
uv run playwright install chromium

# 3. Run
uv run python -m coininfo
```

The service starts on `http://0.0.0.0:8100` by default:

- Dashboard: <http://localhost:8100/>
- Health:    <http://localhost:8100/health>
- API:       <http://localhost:8100/api/coinglass/funding-rates>

> Data accumulates over time — the first scrape cycle runs at startup, then repeats
> every `COINGLASS_SCRAPE_INTERVAL` / `COINGECKO_SCRAPE_INTERVAL` seconds (default 300s).

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up -d --build
# dashboard on http://localhost:8100/
```

The compose file persists the SQLite DB and logs to `./data` and `./logs` on the host.

## Configuration

All configuration is via environment variables (or a `.env` file). Copy
[`.env.example`](./.env.example) and edit. Every value is optional.

| Variable                     | Default              | Description                                                            |
| ---------------------------- | -------------------- | ---------------------------------------------------------------------- |
| `HOST`                       | `0.0.0.0`            | Bind address                                                           |
| `PORT`                       | `8100`               | HTTP port                                                              |
| `LOG_LEVEL`                  | `INFO`               | Log level                                                              |
| `DB_PATH`                    | `data/coininfo.db`   | SQLite path (relative to project root)                                 |
| `COINGLASS_SCRAPE_INTERVAL`  | `300`                | Seconds between CoinGlass scrape cycles                                |
| `COINGECKO_SCRAPE_INTERVAL`  | `300`                | Seconds between CoinGecko fetch cycles                                 |
| `COINGECKO_API_KEY`          | _(empty)_            | Optional CoinGecko demo API key (works without one, just rate-limited) |
| `COINGECKO_TOP_N`            | `250`                | How many top coins to snapshot from CoinGecko                          |
| `DETAIL_COINS`               | `BTC,ETH,SOL`        | Coins to collect in-depth detail for                                   |
| `HTTP_PROXY`                 | _(empty)_            | Optional HTTP/HTTPS proxy for all outbound scraping                    |
| `RETENTION_DAYS`             | `30`                 | Days of history to keep before cleanup                                 |
| `API_KEY`                    | _(empty)_            | If set, every `/api/*` request must send header `X-API-Key: <value>`   |

> **Detail coins note:** the CoinGecko collector maps a small built-in set of symbols
> to CoinGecko IDs (`BTC→bitcoin`, `ETH→ethereum`, `SOL→solana`). To add more detail
> coins, extend `GECKO_IDS` in `src/coininfo/scrapers/coingecko.py`.

## API overview

All data endpoints live under `/api`. When `API_KEY` is set they require an
`X-API-Key` header; otherwise they are open.

| Endpoint                                  | Source              | Returns                          |
| ----------------------------------------- | ------------------- | -------------------------------- |
| `GET /api/coinglass/funding-rates`        | CoinGlass           | Funding rates per exchange       |
| `GET /api/coinglass/open-interest`        | CoinGlass           | Open interest                    |
| `GET /api/coinglass/liquidations`         | CoinGlass           | Long/short liquidations          |
| `GET /api/coinglass/long-short-ratio`     | CoinGlass           | Long/short ratios                |
| `GET /api/coinglass/statistics`           | CoinGlass           | Global market stats              |
| `GET /api/coingecko/markets`              | CoinGecko           | Top-N market snapshot            |
| `GET /api/coingecko/trending`             | CoinGecko           | Trending coins                   |
| `GET /api/coingecko/detail/{symbol}`      | CoinGecko+CoinGlass | Merged in-depth coin detail      |
| `GET /api/coingecko/price/{symbol}`       | CoinGecko           | Latest price for one symbol      |
| `GET /health`                             | —                   | Scraper health / liveness        |

Most endpoints accept `?symbol=BTC` and `?hours=24` (omit `hours` for the latest
snapshot only). Full reference with response schemas: **[docs/API.md](./docs/API.md)**.

## Project layout

```
src/coininfo/
├── __main__.py          # entry point: python -m coininfo
├── main.py              # FastAPI app, lifespan, scraper orchestration, API-key gate
├── config.py            # pydantic-settings configuration
├── db.py                # SQLite schema + async data access (aiosqlite)
├── models.py            # pydantic response models
├── log.py               # structlog + rotating file logging
├── api/                 # FastAPI routers (coinglass / coingecko)
├── scrapers/
│   ├── base.py          # BaseScraper loop
│   ├── coingecko.py     # CoinGecko REST collector
│   └── coinglass.py     # CoinGlass headless-browser collector
└── static/index.html    # dashboard
```

> The internal Python package is named `coininfo` (the project's original name); the
> repository / distribution is `open-coinglass`. Run it with `python -m coininfo`.

## Contributing

Issues and PRs are welcome — especially fixes for CoinGlass selector changes. Please
keep in mind the disclaimer above regarding scraping and Terms of Service.

## License

[MIT](./LICENSE) © 2026 bruce3401
