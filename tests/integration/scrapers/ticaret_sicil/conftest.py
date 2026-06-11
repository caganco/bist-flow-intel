"""Fixtures for TSG integration tests - live DB (same pattern as signals)."""
import pytest_asyncio

import trailing_edge.core.db as _db_mod
from trailing_edge.core.db import get_session, init_db


@pytest_asyncio.fixture(autouse=True)
async def _reset_db_engine():
    """Reset the global engine so it binds to the current event loop."""
    _db_mod._engine = None
    _db_mod._session_factory = None
    yield
    if _db_mod._engine is not None:
        await _db_mod._engine.dispose()
    _db_mod._engine = None
    _db_mod._session_factory = None


@pytest_asyncio.fixture
async def db_session(_reset_db_engine):
    await init_db()
    async with get_session() as session:
        yield session
