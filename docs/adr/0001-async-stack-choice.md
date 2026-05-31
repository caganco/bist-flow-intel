# ADR 0001: Async Stack Choice

**Status:** Accepted  
**Date:** 2026-05-28

## Decision

Use `httpx.AsyncClient` + `asyncio` for HTTP, `asyncpg` + SQLAlchemy 2.0 async for DB.

## Rationale

KAP scraping involves sequential HTTP calls with rate limiting (2 req/s). Async I/O keeps
the event loop busy during network waits without thread overhead. `asyncpg` is the fastest
PostgreSQL driver for Python; SQLAlchemy 2.0 async wraps it cleanly while providing ORM
ergonomics and Alembic migration support.

## Alternatives Rejected

- `requests` + threads: coarser control over rate limiting, worse error handling
- `aiohttp`: less ergonomic than `httpx`, no sync fallback for scripts
- `psycopg3` async: less community tooling for async SQLAlchemy at time of decision
