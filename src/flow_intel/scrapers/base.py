"""Abstract base for all scrapers."""
from abc import ABC, abstractmethod
from datetime import date


class AbstractScraper(ABC):
    @abstractmethod
    async def run(self, from_date: date, to_date: date) -> None:
        raise NotImplementedError
