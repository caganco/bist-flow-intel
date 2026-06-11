"""Async SQLAlchemy engine and session factory."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from trailing_edge.core.config import get_config
from trailing_edge.core.logging import get_logger

_log = get_logger(__name__)
_engine = None
_session_factory: async_sessionmaker | None = None


def _get_engine():
    global _engine, _session_factory
    if _engine is None:
        cfg = get_config()
        url = cfg["db"]["url"]
        pool_size = int(cfg["db"].get("pool_size", 5))
        max_overflow = int(cfg["db"].get("max_overflow", 10))
        _engine = create_async_engine(
            url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            echo=False,
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    _get_engine()
    assert _session_factory is not None
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    engine = _get_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    _log.info("db_connected")
