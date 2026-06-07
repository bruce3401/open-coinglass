# API Reference

[English](./API.md) | [简体中文](./API.zh-CN.md)

Base URL: `http://<host>:<port>` (default `http://localhost:8100`).

## Authentication

If the `API_KEY` environment variable is set, **every** `/api/*` request must include
the header:

```
X-API-Key: <your key>
```

Requests without a valid key receive `401`. The `/health` endpoint and the dashboard
are **not** gated. If `API_KEY` is empty, the API is open.

```bash
curl -H "X-API-Key: $API_KEY" "http://localhost:8100/api/coinglass/funding-rates?symbol=BTC"
```

## Common conventions

- All responses (except `/health`) are wrapped in an envelope:

  ```json
  { "data": <payload>, "source": "<origin>" }
  ```

- **Time fields** (`ts`) are ISO-8601 UTC strings, e.g. `2026-01-31T12:00:00+00:00`.
- **`hours` query parameter** (where supported):
  - omitted → return only the **latest snapshot** (the most recent scrape batch);
  - provided (e.g. `hours=24`) → return **all rows within the last N hours**, newest first.
- **`symbol` query parameter** is case-insensitive (`btc` == `BTC`).
- Monetary values are in **USD**. Funding `rate` is a fraction (e.g. `0.0001` = 0.01%).

---

## CoinGlass endpoints

### `GET /api/coinglass/funding-rates`

Funding rate per exchange.

| Query    | Type   | Notes                                  |
| -------- | ------ | -------------------------------------- |
| `symbol` | string | optional, filter by coin               |
| `hours`  | number | optional, history window in hours      |

```json
{
  "data": [
    { "ts": "2026-01-31T12:00:00+00:00", "symbol": "BTC", "exchange": "Binance", "rate": 0.0001 }
  ],
  "source": "coinglass"
}
```

### `GET /api/coinglass/open-interest`

Open interest. `exchange` is `"all"` for the aggregated homepage figure, or a specific
exchange name for per-exchange detail rows. `change_24h_pct` may be `null`.

| Query    | Type   | Notes                              |
| -------- | ------ | ---------------------------------- |
| `symbol` | string | optional                           |
| `hours`  | number | optional                           |

```json
{
  "data": [
    { "ts": "2026-01-31T12:00:00+00:00", "symbol": "BTC", "exchange": "all", "oi_usd": 38500000000, "change_24h_pct": 1.23 }
  ],
  "source": "coinglass"
}
```

### `GET /api/coinglass/liquidations`

Long/short liquidation totals (24h, USD).

| Query    | Type   | Notes    |
| -------- | ------ | -------- |
| `symbol` | string | optional |
| `hours`  | number | optional |

```json
{
  "data": [
    { "ts": "2026-01-31T12:00:00+00:00", "symbol": "BTC", "long_liq_usd": 12000000, "short_liq_usd": 8000000, "total_liq_usd": 20000000 }
  ],
  "source": "coinglass"
}
```

### `GET /api/coinglass/long-short-ratio`

Long/short ratios. `account` is one of `retail`, `whale_account`, `whale_position`.
`long_pct` / `short_pct` are derived from `ratio` and sum to 1.0.

| Query    | Type   | Notes    |
| -------- | ------ | -------- |
| `symbol` | string | optional |
| `hours`  | number | optional |

```json
{
  "data": [
    { "ts": "2026-01-31T12:00:00+00:00", "symbol": "BTC", "account": "retail", "ratio": 2.0989, "long_pct": 0.677, "short_pct": 0.323 }
  ],
  "source": "coinglass"
}
```

### `GET /api/coinglass/statistics`

Global market stats.

| Query   | Type   | Notes                                          |
| ------- | ------ | ---------------------------------------------- |
| `hours` | number | optional; omitted → latest single row          |

```json
{
  "data": [
    { "ts": "2026-01-31T12:00:00+00:00", "total_oi_usd": 120000000000, "total_volume_24h_usd": 250000000000, "total_liq_24h_usd": 350000000 }
  ],
  "source": "coinglass"
}
```

---

## CoinGecko endpoints

### `GET /api/coingecko/markets`

Top-N market snapshot, ordered by market-cap rank.

| Query    | Type   | Notes                                |
| -------- | ------ | ------------------------------------ |
| `limit`  | int    | optional, 1–500, default `100`       |
| `symbol` | string | optional, filter to one coin         |

```json
{
  "data": [
    { "symbol": "btc", "name": "Bitcoin", "price_usd": 95000.0, "market_cap_usd": 1880000000000, "market_cap_rank": 1, "volume_24h_usd": 30000000000, "pct_24h": 1.5 }
  ],
  "source": "coingecko"
}
```

### `GET /api/coingecko/trending`

Currently trending coins (lower `score` = higher rank).

```json
{
  "data": [
    { "symbol": "xyz", "name": "Example", "market_cap_rank": 142, "score": 0 }
  ],
  "source": "coingecko"
}
```

### `GET /api/coingecko/detail/{symbol}`

Merged in-depth detail (CoinGecko fields + CoinGlass futures/spot volumes) for a coin
in `DETAIL_COINS`. Any field may be `null` if unavailable.

| Path / Query | Type   | Notes                                |
| ------------ | ------ | ------------------------------------ |
| `symbol`     | path   | e.g. `BTC`                           |
| `hours`      | number | optional; omitted → latest snapshot  |

```json
{
  "data": [
    {
      "ts": "2026-01-31T12:00:00+00:00", "symbol": "BTC",
      "price_usd": 95000.0, "high_24h": 96000.0, "low_24h": 94000.0,
      "pct_1h": 0.2, "pct_24h": 1.5, "pct_7d": 5.0, "pct_14d": 8.0, "pct_30d": 12.0,
      "market_cap_usd": 1880000000000, "market_cap_rank": 1,
      "volume_24h_usd": 30000000000, "futures_vol_24h_usd": 50000000000, "spot_vol_24h_usd": 12000000000,
      "circulating_supply": 19800000, "max_supply": 21000000,
      "sentiment_up_pct": 78.0, "sentiment_down_pct": 22.0
    }
  ],
  "source": "coingecko+coinglass"
}
```

### `GET /api/coingecko/price/{symbol}`

Latest price for a single symbol (from the markets snapshot). `data` is `null` if the
symbol is not in the current snapshot.

```json
{
  "data": { "symbol": "btc", "name": "Bitcoin", "price_usd": 95000.0, "market_cap_usd": 1880000000000, "market_cap_rank": 1, "volume_24h_usd": 30000000000, "pct_24h": 1.5 },
  "source": "coingecko"
}
```

---

## Health

### `GET /health`

Liveness + per-scraper status. **Not** wrapped in the `data`/`source` envelope and
**not** gated by `API_KEY`.

```json
{
  "status": "ok",
  "scrapers": [
    { "source": "coingecko", "last_success": "2026-01-31T12:00:00+00:00", "last_error": null, "consecutive_errors": 0 },
    { "source": "coinglass", "last_success": "2026-01-31T11:55:00+00:00", "last_error": null, "consecutive_errors": 0 }
  ]
}
```

## Interactive docs

FastAPI auto-generates OpenAPI docs:

- Swagger UI: `http://localhost:8100/docs`
- ReDoc:      `http://localhost:8100/redoc`
- OpenAPI:    `http://localhost:8100/openapi.json`
