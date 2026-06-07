# API 参考

[English](./API.md) | [简体中文](./API.zh-CN.md)

基础地址：`http://<host>:<port>`（默认 `http://localhost:8100`）。

## 鉴权

如果设置了环境变量 `API_KEY`，则**每个** `/api/*` 请求都必须带上请求头：

```
X-API-Key: <你的 key>
```

未携带有效 key 的请求返回 `401`。`/health` 接口和仪表盘**不**受鉴权限制。若 `API_KEY` 为空，
则 API 开放访问。

```bash
curl -H "X-API-Key: $API_KEY" "http://localhost:8100/api/coinglass/funding-rates?symbol=BTC"
```

## 通用约定

- 除 `/health` 外，所有响应都包在统一信封里：

  ```json
  { "data": <负载>, "source": "<来源>" }
  ```

- **时间字段**（`ts`）为 ISO-8601 UTC 字符串，例如 `2026-01-31T12:00:00+00:00`。
- **`hours` 查询参数**（支持的接口）：
  - 不传 → 只返回**最新快照**（最近一次采集批次）；
  - 传值（如 `hours=24`）→ 返回**最近 N 小时内的所有记录**，最新在前。
- **`symbol` 查询参数**大小写不敏感（`btc` == `BTC`）。
- 金额单位为 **USD**。资金费率 `rate` 是小数（如 `0.0001` 表示 0.01%）。

---

## CoinGlass 接口

### `GET /api/coinglass/funding-rates`

各交易所资金费率。

| 查询参数 | 类型   | 说明                       |
| -------- | ------ | -------------------------- |
| `symbol` | string | 可选，按币种过滤           |
| `hours`  | number | 可选，历史时间窗口（小时） |

```json
{
  "data": [
    { "ts": "2026-01-31T12:00:00+00:00", "symbol": "BTC", "exchange": "Binance", "rate": 0.0001 }
  ],
  "source": "coinglass"
}
```

### `GET /api/coinglass/open-interest`

持仓量。`exchange` 为 `"all"` 表示首页聚合值，或为具体交易所名（逐交易所明细）。
`change_24h_pct` 可能为 `null`。

| 查询参数 | 类型   | 说明 |
| -------- | ------ | ---- |
| `symbol` | string | 可选 |
| `hours`  | number | 可选 |

```json
{
  "data": [
    { "ts": "2026-01-31T12:00:00+00:00", "symbol": "BTC", "exchange": "all", "oi_usd": 38500000000, "change_24h_pct": 1.23 }
  ],
  "source": "coinglass"
}
```

### `GET /api/coinglass/liquidations`

多空爆仓合计（24h，USD）。

| 查询参数 | 类型   | 说明 |
| -------- | ------ | ---- |
| `symbol` | string | 可选 |
| `hours`  | number | 可选 |

```json
{
  "data": [
    { "ts": "2026-01-31T12:00:00+00:00", "symbol": "BTC", "long_liq_usd": 12000000, "short_liq_usd": 8000000, "total_liq_usd": 20000000 }
  ],
  "source": "coinglass"
}
```

### `GET /api/coinglass/long-short-ratio`

多空比。`account` 取值为 `retail`、`whale_account`、`whale_position` 之一。
`long_pct` / `short_pct` 由 `ratio` 推导，两者之和为 1.0。

| 查询参数 | 类型   | 说明 |
| -------- | ------ | ---- |
| `symbol` | string | 可选 |
| `hours`  | number | 可选 |

```json
{
  "data": [
    { "ts": "2026-01-31T12:00:00+00:00", "symbol": "BTC", "account": "retail", "ratio": 2.0989, "long_pct": 0.677, "short_pct": 0.323 }
  ],
  "source": "coinglass"
}
```

### `GET /api/coinglass/statistics`

全局市场统计。

| 查询参数 | 类型   | 说明                            |
| -------- | ------ | ------------------------------- |
| `hours`  | number | 可选；不传 → 仅返回最新一行      |

```json
{
  "data": [
    { "ts": "2026-01-31T12:00:00+00:00", "total_oi_usd": 120000000000, "total_volume_24h_usd": 250000000000, "total_liq_24h_usd": 350000000 }
  ],
  "source": "coinglass"
}
```

---

## CoinGecko 接口

### `GET /api/coingecko/markets`

Top-N 市场快照，按市值排名排序。

| 查询参数 | 类型   | 说明                         |
| -------- | ------ | ---------------------------- |
| `limit`  | int    | 可选，1–500，默认 `100`      |
| `symbol` | string | 可选，过滤到单个币种         |

```json
{
  "data": [
    { "symbol": "btc", "name": "Bitcoin", "price_usd": 95000.0, "market_cap_usd": 1880000000000, "market_cap_rank": 1, "volume_24h_usd": 30000000000, "pct_24h": 1.5 }
  ],
  "source": "coingecko"
}
```

### `GET /api/coingecko/trending`

当前趋势币（`score` 越小排名越靠前）。

```json
{
  "data": [
    { "symbol": "xyz", "name": "Example", "market_cap_rank": 142, "score": 0 }
  ],
  "source": "coingecko"
}
```

### `GET /api/coingecko/detail/{symbol}`

`DETAIL_COINS` 中某币种的合并深度详情（CoinGecko 字段 + CoinGlass 期货/现货成交量）。
任一字段在不可用时可能为 `null`。

| 路径 / 查询 | 类型   | 说明                          |
| ----------- | ------ | ----------------------------- |
| `symbol`    | path   | 如 `BTC`                      |
| `hours`     | number | 可选；不传 → 最新快照         |

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

单个币种的最新价（取自市场快照）。若该币种不在当前快照中，`data` 为 `null`。

```json
{
  "data": { "symbol": "btc", "name": "Bitcoin", "price_usd": 95000.0, "market_cap_usd": 1880000000000, "market_cap_rank": 1, "volume_24h_usd": 30000000000, "pct_24h": 1.5 },
  "source": "coingecko"
}
```

---

## 健康检查

### `GET /health`

存活检查 + 各采集器状态。**不**包在 `data`/`source` 信封里，也**不**受 `API_KEY` 限制。

```json
{
  "status": "ok",
  "scrapers": [
    { "source": "coingecko", "last_success": "2026-01-31T12:00:00+00:00", "last_error": null, "consecutive_errors": 0 },
    { "source": "coinglass", "last_success": "2026-01-31T11:55:00+00:00", "last_error": null, "consecutive_errors": 0 }
  ]
}
```

## 交互式文档

FastAPI 自动生成 OpenAPI 文档：

- Swagger UI：`http://localhost:8100/docs`
- ReDoc：`http://localhost:8100/redoc`
- OpenAPI：`http://localhost:8100/openapi.json`
