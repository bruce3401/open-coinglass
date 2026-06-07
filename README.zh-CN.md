# open-coinglass

> 一个可自托管的加密货币**衍生品数据聚合服务**。它从 [CoinGlass](https://www.coinglass.com)
> 采集资金费率、持仓量、爆仓、多空比和市场统计，再用 [CoinGecko](https://www.coingecko.com)
> 公开 API 补充现货/行情数据，全部存入本地 SQLite，并通过一个轻量 REST API 和内置仪表盘对外提供。

[English](./README.md) | 简体中文

---

## ⚠️ 免责声明 —— 请先阅读

- 本项目**仅供个人学习、研究用途**。
- 本项目**与 CoinGlass、CoinGecko 没有任何关联，也未获得其授权或背书**。"CoinGlass" 与
  "CoinGecko" 为各自权利人的商标。
- CoinGlass 采集是通过**无头浏览器渲染公开网页并读取 DOM** 实现的（CoinGlass 未对这些数据
  提供免费公开 API）。抓取行为可能违反目标网站的服务条款（ToS）。**你需要为如何使用本软件负责。**
  请查阅并遵守你所指向网站的 ToS 与 `robots.txt`，并保持合理的请求频率。
- 本软件按**"原样"（AS IS）提供，不附带任何形式的担保**（见 [LICENSE](./LICENSE)）。
- **维护说明：** 这是一个尽力而为、低频维护的项目。DOM 抓取天生脆弱——当 CoinGlass 改版页面
  结构时，CoinGlass 相关采集可能失效，需更新选择器后才能恢复。CoinGecko 一侧使用官方公开 API，
  稳定得多。

---

## 功能特性

- **CoinGlass 指标**（无头浏览器 DOM 提取）
  - 各交易所资金费率
  - 持仓量 OI（全局 + 单币种 + 各交易所）
  - 爆仓（多 / 空，24h）
  - 多空比（散户账户、大户账户、大户持仓三类）
  - 全局市场统计（总 OI、24h 成交量、24h 爆仓）
- **CoinGecko 指标**（官方公开 API）
  - Top-N 市场快照（价格、市值、排名、24h 成交量、24h 涨跌）
  - 趋势币
  - 可配置币种（默认 `BTC,ETH,SOL`）的深度详情：价格、最高/最低、1h–30d 涨跌幅、供应量、情绪
- **历史存储**：SQLite，自动按保留期清理
- **REST API**（FastAPI），可选 `X-API-Key` 鉴权
- **内置仪表盘**（单个静态 HTML，Chart.js），便于快速可视化
- **Docker / docker-compose** 部署，支持可选 HTTP 代理

## 架构

```
                +-------------------+        +-------------------+
   CoinGlass    |  CoinGlassScraper |        | CoinGeckoScraper  |   CoinGecko
   (网页)        |  (Playwright DOM) |        |   (REST/aiohttp)  |   (公开 API)
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
                    |        FastAPI 应用 (uvicorn)           |
                    |   /api/coinglass/*   /api/coingecko/*   |
                    |   /health            /  (仪表盘)        |
                    +-----------------------------------------+
```

每个采集器都是独立的 asyncio 循环，按各自的间隔运行；第三个循环周期性删除超过 `RETENTION_DAYS`
的旧数据。完整接口见 [docs/API.zh-CN.md](./docs/API.zh-CN.md)。

## 环境要求

- Python **3.11+**
- [`uv`](https://github.com/astral-sh/uv)（推荐）——或任意基于 pip 的方式
- Chromium（通过 `playwright install chromium` 自动安装）
- 可选：Docker / docker-compose

## 快速开始（本地，使用 uv）

```bash
git clone https://github.com/bruce3401/open-coinglass.git
cd open-coinglass

# 1. 配置（所有项都可选，默认值已经合理）
cp .env.example .env

# 2. 安装依赖 + Chromium
uv sync
uv run playwright install chromium

# 3. 运行
uv run python -m coininfo
```

服务默认监听 `http://0.0.0.0:8100`：

- 仪表盘：<http://localhost:8100/>
- 健康检查：<http://localhost:8100/health>
- API：<http://localhost:8100/api/coinglass/funding-rates>

> 数据是随时间累积的——启动时跑第一轮采集，之后每隔
> `COINGLASS_SCRAPE_INTERVAL` / `COINGECKO_SCRAPE_INTERVAL` 秒重复一次（默认 300 秒）。

## 快速开始（Docker）

```bash
cp .env.example .env
docker compose up -d --build
# 仪表盘 http://localhost:8100/
```

compose 会把 SQLite 数据库和日志持久化到宿主机的 `./data` 和 `./logs`。

## 配置项

全部通过环境变量（或 `.env` 文件）配置。复制 [`.env.example`](./.env.example) 修改即可，每项都可选。

| 变量                          | 默认值               | 说明                                                     |
| ----------------------------- | -------------------- | -------------------------------------------------------- |
| `HOST`                        | `0.0.0.0`            | 监听地址                                                 |
| `PORT`                        | `8100`               | HTTP 端口                                                |
| `LOG_LEVEL`                   | `INFO`               | 日志级别                                                 |
| `DB_PATH`                     | `data/coininfo.db`   | SQLite 路径（相对项目根目录）                            |
| `COINGLASS_SCRAPE_INTERVAL`   | `300`                | CoinGlass 采集周期（秒）                                  |
| `COINGECKO_SCRAPE_INTERVAL`   | `300`                | CoinGecko 拉取周期（秒）                                  |
| `COINGECKO_API_KEY`           | _(空)_               | 可选的 CoinGecko demo API key（不填也能用，只是受限）   |
| `COINGECKO_TOP_N`             | `250`                | 从 CoinGecko 快照的头部币种数量                          |
| `DETAIL_COINS`                | `BTC,ETH,SOL`        | 采集深度详情的币种                                       |
| `HTTP_PROXY`                  | _(空)_               | 可选的出站抓取 HTTP/HTTPS 代理                            |
| `RETENTION_DAYS`              | `30`                 | 历史数据保留天数（超期清理）                            |
| `API_KEY`                     | _(空)_               | 若设置，则所有 `/api/*` 请求须带 `X-API-Key: <值>` 头   |

> **关于详情币种：** CoinGecko 采集器内置了一小张符号→CoinGecko ID 的映射
> （`BTC→bitcoin`、`ETH→ethereum`、`SOL→solana`）。如需增加详情币种，请扩展
> `src/coininfo/scrapers/coingecko.py` 里的 `GECKO_IDS`。

## API 概览

所有数据接口都在 `/api` 下。当设置了 `API_KEY` 时需要带 `X-API-Key` 头，否则开放访问。

| 接口                                       | 数据源              | 返回                       |
| ------------------------------------------ | ------------------- | -------------------------- |
| `GET /api/coinglass/funding-rates`         | CoinGlass           | 各交易所资金费率           |
| `GET /api/coinglass/open-interest`         | CoinGlass           | 持仓量                     |
| `GET /api/coinglass/liquidations`          | CoinGlass           | 多空爆仓                   |
| `GET /api/coinglass/long-short-ratio`      | CoinGlass           | 多空比                     |
| `GET /api/coinglass/statistics`            | CoinGlass           | 全局市场统计               |
| `GET /api/coingecko/markets`               | CoinGecko           | Top-N 市场快照             |
| `GET /api/coingecko/trending`              | CoinGecko           | 趋势币                     |
| `GET /api/coingecko/detail/{symbol}`       | CoinGecko+CoinGlass | 合并后的深度详情           |
| `GET /api/coingecko/price/{symbol}`        | CoinGecko           | 单个币种最新价             |
| `GET /health`                              | —                   | 采集器健康/存活检查        |

大多数接口支持 `?symbol=BTC` 和 `?hours=24`（不带 `hours` 则只返回最新快照）。
完整参考与响应结构见 **[docs/API.zh-CN.md](./docs/API.zh-CN.md)**。

## 目录结构

```
src/coininfo/
├── __main__.py          # 入口：python -m coininfo
├── main.py              # FastAPI 应用、生命周期、采集编排、API-key 鉴权
├── config.py            # pydantic-settings 配置
├── db.py                # SQLite 表结构 + 异步数据访问 (aiosqlite)
├── models.py            # pydantic 响应模型
├── log.py               # structlog + 滚动文件日志
├── api/                 # FastAPI 路由 (coinglass / coingecko)
├── scrapers/
│   ├── base.py          # BaseScraper 循环
│   ├── coingecko.py     # CoinGecko REST 采集器
│   └── coinglass.py     # CoinGlass 无头浏览器采集器
└── static/index.html    # 仪表盘
```

> 内部 Python 包名为 `coininfo`（项目最初的名字）；仓库 / 发行名为 `open-coinglass`。
> 运行命令是 `python -m coininfo`。

## 参与贡献

欢迎提 Issue 和 PR——尤其是 CoinGlass 选择器变更后的修复。请注意上文关于抓取与服务条款的免责声明。

## 许可证

[MIT](./LICENSE) © 2026 bruce3401
