from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from coininfo.api.deps import get_db
from coininfo.db import Database
from coininfo.models import DataResponse, FundingRate, LiquidationRecord, LongShortRecord, MarketStats, OpenInterestRecord

router = APIRouter()


@router.get("/funding-rates")
async def get_funding_rates(
    symbol: str | None = Query(None),
    hours: float | None = Query(None, description="History window in hours"),
    db: Database = Depends(get_db),
) -> DataResponse[list[FundingRate]]:
    return DataResponse(data=await db.get_funding_rates(symbol, hours), source="coinglass")


@router.get("/open-interest")
async def get_open_interest(
    symbol: str | None = Query(None),
    hours: float | None = Query(None),
    db: Database = Depends(get_db),
) -> DataResponse[list[OpenInterestRecord]]:
    return DataResponse(data=await db.get_open_interest(symbol, hours), source="coinglass")


@router.get("/liquidations")
async def get_liquidations(
    symbol: str | None = Query(None),
    hours: float | None = Query(None),
    db: Database = Depends(get_db),
) -> DataResponse[list[LiquidationRecord]]:
    return DataResponse(data=await db.get_liquidations(symbol, hours), source="coinglass")


@router.get("/long-short-ratio")
async def get_long_short_ratio(
    symbol: str | None = Query(None),
    hours: float | None = Query(None),
    db: Database = Depends(get_db),
) -> DataResponse[list[LongShortRecord]]:
    return DataResponse(data=await db.get_long_short_ratio(symbol, hours), source="coinglass")


@router.get("/statistics")
async def get_market_stats(
    hours: float | None = Query(None),
    db: Database = Depends(get_db),
) -> DataResponse[list[MarketStats]]:
    return DataResponse(data=await db.get_market_stats(hours), source="coinglass")
