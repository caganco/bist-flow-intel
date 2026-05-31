"""Unit tests for 2captcha solver module."""
import pytest


def test_get_solver_raises_without_key(monkeypatch):
    """Missing TWOCAPTCHA_API_KEY → RuntimeError with clear message."""
    monkeypatch.delenv("TWOCAPTCHA_API_KEY", raising=False)
    import flow_intel.scrapers.ticaret_sicil.captcha as cm
    cm._solver = None  # reset singleton
    with pytest.raises(RuntimeError, match="TWOCAPTCHA_API_KEY"):
        cm.get_solver()


@pytest.mark.asyncio
async def test_solve_captcha_on_page_no_element():
    """When CAPTCHA img not found → None (safe no-op, no API call)."""
    from unittest.mock import AsyncMock, MagicMock

    page = MagicMock()
    page.query_selector = AsyncMock(return_value=None)

    from flow_intel.scrapers.ticaret_sicil.captcha import solve_captcha_on_page

    result = await solve_captcha_on_page(page)
    assert result is None
    # query_selector called but solver never invoked (no API key needed)
    page.query_selector.assert_called_once()
