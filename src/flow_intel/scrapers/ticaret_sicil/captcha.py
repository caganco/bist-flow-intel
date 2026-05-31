"""2captcha image CAPTCHA solver for TSG Playwright flows.

Recon (TASK-007 S2.5) confirmed:
- CAPTCHA required only for the one-time login (FormUyeGirisi).
- Search form (FormIlanGoruntuleme) and PDF popup have NO CAPTCHA for
  authenticated users. 2captcha is therefore called once per scraper run.

Selectors confirmed:
  img:  img#CaptchaImg  (first match = login modal)
  input: input#Captcha  (maxlength=4, login modal)
  submit: button.c-btn-login
"""
from __future__ import annotations

import asyncio
import base64
import os

from flow_intel.core.logging import get_logger

_log = get_logger(__name__)

_solver = None  # TwoCaptcha singleton


def get_solver():
    global _solver
    if _solver is None:
        from twocaptcha import TwoCaptcha

        api_key = os.environ.get("TWOCAPTCHA_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "TWOCAPTCHA_API_KEY not set. "
                "Add to .env: TWOCAPTCHA_API_KEY=your_key"
            )
        _solver = TwoCaptcha(api_key)
    return _solver


async def solve_captcha_on_page(
    page,
    img_selector: str = "img#CaptchaImg",
    input_selector: str = "input#Captcha",
) -> str | None:
    """Screenshot the CAPTCHA image on a Playwright page, solve via 2captcha,
    fill the answer into the input field, and return the solved text.

    Returns None if no CAPTCHA image is found (safe no-op — call freely).
    Raises RuntimeError if API key is missing and a CAPTCHA is present.

    Uses element screenshot (not GET captcha.php URL) so the image is always
    the one currently rendered for this session — no cookie/session confusion.
    """
    img = await page.query_selector(img_selector)
    if img is None:
        return None

    png_bytes = await img.screenshot()
    b64 = base64.b64encode(png_bytes).decode()

    solver = get_solver()

    def _sync_solve() -> str:
        result = solver.normal(b64)
        return result["code"]

    code = await asyncio.get_event_loop().run_in_executor(None, _sync_solve)
    _log.info("captcha_solved", chars=len(code))

    if input_selector:
        inp = await page.query_selector(input_selector)
        if inp:
            await inp.fill(code)

    return code
