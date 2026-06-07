from __future__ import annotations

import hmac

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from coininfo.config import load_settings
from coininfo.db import Database

_db: Database | None = None


async def get_db() -> Database:
    assert _db is not None, "Database not initialized"
    return _db


def set_db(db: Database) -> None:
    global _db
    _db = db


_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(provided: str | None = Security(_api_key_header)) -> None:
    expected = load_settings().api_key
    if expected is None:
        return
    if provided is None or not hmac.compare_digest(provided, expected.get_secret_value()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing X-API-Key")
