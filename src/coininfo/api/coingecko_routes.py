from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from coininfo.api.deps import get_db
from coininfo.db import Database
from coininfo.models import CoinDetail, CoinMarket, DataResponse, TrendingCoin

router = APIRouter()


@router.get("/markets")
async def get_markets(
    limit: int = Query(100, ge=1, le=500),
    symbol: str | None = Query(None),
    db: Database = Depends(get_db),
) -> DataResponse[list[CoinMarket]]:
    return DataResponse(data=await db.get_coin_markets(limit, symbol), source="coingecko")


@router.get("/trending")
async def get_trending(db: Database = Depends(get_db)) -> DataResponse[list[TrendingCoin]]:
    return DataResponse(data=await db.get_trending(), source="coingecko")


@router.get("/detail/{symbol}")
async def get_detail(
    symbol: str,
    hours: float | None = Query(None),
    db: Database = Depends(get_db),
) -> DataResponse[list[CoinDetail]]:
    return DataResponse(data=await db.get_coin_detail(symbol, hours), source="coingecko+coinglass")


@router.get("/price/{symbol}")
async def get_price(symbol: str, db: Database = Depends(get_db)) -> DataResponse[CoinMarket | None]:
    coins = await db.get_coin_markets(limit=1, symbol=symbol)
    return DataResponse(data=coins[0] if coins else None, source="coingecko")
