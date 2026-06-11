"""Abstract base for all scrapers."""
from abc import ABC, abstractmethod
from datetime import date
from typing import Generic, TypeVar

ResultT = TypeVar("ResultT")


class AbstractScraper(ABC, Generic[ResultT]):
    @abstractmethod
    async def run(self, from_date: date, to_date: date) -> ResultT:
        raise NotImplementedError
