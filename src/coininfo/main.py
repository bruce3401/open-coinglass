from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from coininfo.api.coingecko_routes import router as coingecko_router
from coininfo.api.coinglass_routes import router as coinglass_router
from coininfo.api.deps import get_db, require_api_key, set_db
from coininfo.config import load_settings
from coininfo.db import Database
from coininfo.log import get_logger, setup_logging
from coininfo.scrapers.coingecko import CoinGeckoScraper
from coininfo.scrapers.coinglass import CoinGlassScraper

logger = get_logger("main")


async def _cleanup_loop(db: Database, retention_days: int) -> None:
    """Run cleanup every 6 hours."""
    while True:
        try:
            await db.cleanup(retention_days)
        except Exception as e:
            logger.warning("cleanup_error", error=str(e))
        await asyncio.sleep(6 * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    log_path = settings.log_file
    if log_path and not Path(log_path).is_absolute():
        log_path = str(Path(__file__).parent.parent.parent / log_path)
    setup_logging(settings.log_level, log_path)
    logger.info("starting", host=settings.host, port=settings.port)

    db = Database(settings.db_abs_path)
    await db.initialize()
    set_db(db)

    proxy = settings.http_proxy
    detail_coins = [c.strip().upper() for c in settings.detail_coins.split(",") if c.strip()]
    api_key = settings.coingecko_api_key.get_secret_value() if settings.coingecko_api_key else None

    coingecko = CoinGeckoScraper(
        db=db, interval=settings.coingecko_scrape_interval,
        api_key=api_key, top_n=settings.coingecko_top_n,
        proxy=proxy, detail_coins=detail_coins,
    )
    coinglass = CoinGlassScraper(
        db=db, interval=settings.coinglass_scrape_interval,
        proxy=proxy, detail_coins=detail_coins,
    )

    await coingecko.setup()
    await coinglass.setup()

    tasks = [
        asyncio.create_task(coingecko.run_loop(), name="coingecko"),
        asyncio.create_task(coinglass.run_loop(), name="coinglass"),
        asyncio.create_task(_cleanup_loop(db, settings.retention_days), name="cleanup"),
    ]

    logger.info("scrapers_started", detail_coins=detail_coins)
    yield

    coingecko.stop()
    coinglass.stop()
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await coingecko.teardown()
    await coinglass.teardown()
    await db.close()
    logger.info("shutdown_complete")


app = FastAPI(
    title="open-coinglass",
    description="Self-hosted crypto derivatives data aggregator (CoinGlass + CoinGecko)",
    version="0.2.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health(db: Database = Depends(get_db)):
    meta = await db.get_scrape_health()
    return {"status": "ok", "scrapers": [m.model_dump() for m in meta]}


# API routes (gated by X-API-Key when settings.api_key is set)
api_router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])
api_router.include_router(coinglass_router, prefix="/coinglass", tags=["coinglass"])
api_router.include_router(coingecko_router, prefix="/coingecko", tags=["coingecko"])
app.include_router(api_router)

# Static dashboard (must be last — catch-all mount)
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
