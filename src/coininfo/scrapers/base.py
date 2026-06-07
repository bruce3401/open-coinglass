from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from coininfo.db import Database
from coininfo.log import get_logger


class BaseScraper(ABC):
    def __init__(self, db: Database, interval: int, name: str) -> None:
        self.db = db
        self.interval = interval
        self.name = name
        self.logger = get_logger(f"scraper.{name}")
        self._running = False

    async def run_loop(self) -> None:
        self._running = True
        self.logger.info("scraper_started", interval=self.interval)
        while self._running:
            try:
                await self.scrape()
                await self.db.update_scrape_meta(self.name, success=True)
                self.logger.info("scrape_success")
            except Exception as e:
                await self.db.update_scrape_meta(self.name, success=False, error=str(e))
                self.logger.exception("scrape_error", error=str(e))
            await asyncio.sleep(self.interval)

    @abstractmethod
    async def scrape(self) -> None: ...

    @abstractmethod
    async def setup(self) -> None: ...

    @abstractmethod
    async def teardown(self) -> None: ...

    def stop(self) -> None:
        self._running = False
