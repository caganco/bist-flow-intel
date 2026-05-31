"""Fixtures for reports integration tests — connects to the live DB."""
import pytest_asyncio

import flow_intel.core.db as _db_mod
from flow_intel.core.db import get_session, init_db


@pytest_asyncio.fixture(autouse=True)
async def _reset_db_engine():
    """Reset global engine before each test so it binds to the current event loop."""
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
