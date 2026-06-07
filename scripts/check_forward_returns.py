"""Forward return checker - cluster detection sonrasi hisse performansi.

Her cluster icin:
  - Tespit tarihi (window_start) ve score
  - +20 islem gunu sonraki getiri (yfinance BIST)
  - Sonuc: YUKSELDI / DUSTU / BEKLIYOR

Kullanim:
    uv run python scripts/check_forward_returns.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

try:
    import yfinance as yf
except ImportError:
    print("yfinance eksik: uv add yfinance")
    sys.exit(1)

# Kac islem gunu sonrasini olcuyoruz
FORWARD_DAYS = 20
# Bu kadandan once tespit edilmis cluster'lara bakiyoruz (daha yeni = "BEKLIYOR")
MIN_DAYS_AGO = FORWARD_DAYS + 5


def _trading_price(ticker_is: str, target_date: date) -> float | None:
    """target_date civarindaki kapani fiyatini dondur (BIST, .IS suffix)."""
    start = target_date - timedelta(days=5)
    end = target_date + timedelta(days=5)
    try:
        hist = yf.download(ticker_is, start=start, end=end, progress=False, auto_adjust=True)
        if hist.empty:
            return None
        # Hedef tarihe en yakin kapanisi al
        hist.index = hist.index.date
        dates = [d for d in hist.index if d <= target_date]
        if not dates:
            dates = list(hist.index)
        closest = max(dates)
        close = hist.loc[closest, "Close"]
        val = float(close.iloc[0]) if hasattr(close, "iloc") else float(close)
        return val if val > 0 else None
    except Exception:
        return None


async def _get_clusters() -> list[dict]:
    from flow_intel.core.db import get_session, init_db
    from sqlalchemy import text

    await init_db()
    async with get_session() as session:
        rows = (await session.execute(text(
            "SELECT ticker, MIN(window_start) AS first_detected, "
            "MAX(cluster_score) AS top_score, MAX(insider_count) AS max_insiders "
            "FROM insider_clusters "
            "GROUP BY ticker ORDER BY top_score DESC"
        ))).all()
    return [
        {
            "ticker": r.ticker,
            "detected": r.first_detected,
            "score": float(r.top_score),
            "insiders": r.max_insiders,
        }
        for r in rows
    ]


def _check_returns(clusters: list[dict]) -> list[dict]:
    today = date.today()
    results = []
    for c in clusters:
        detected: date = c["detected"]
        ticker_is = f"{c['ticker']}.IS"
        days_ago = (today - detected).days

        if days_ago < MIN_DAYS_AGO:
            results.append({**c, "p0": None, "p20": None, "ret": None, "status": "BEKLIYOR"})
            continue

        target_20d = detected + timedelta(days=FORWARD_DAYS * 1.4)  # ~20 islem gunu ~ 28 takvim gunu
        p0 = _trading_price(ticker_is, detected)
        p20 = _trading_price(ticker_is, target_20d.date() if hasattr(target_20d, "date") else target_20d)

        if p0 and p20:
            ret = (p20 - p0) / p0 * 100
            status = "YUKSELDI" if ret >= 0 else "DUSTU"
        else:
            ret = None
            status = "VERI YOK"

        results.append({**c, "p0": p0, "p20": p20, "ret": ret, "status": status})
    return results


def _print_table(results: list[dict]) -> None:
    today = date.today()
    header = f"{'TICKER':<8} {'SCORE':>6} {'INS':>4} {'TESPIT':>12} {'P0':>10} {'P+20':>10} {'GETIRI':>8}  DURUM"
    print()
    print(f"=== Forward Return Analizi ({today}) - {FORWARD_DAYS} islem gunu ===")
    print(header)
    print("-" * len(header))

    for r in results:
        p0_str  = f"{r['p0']:.2f}" if r["p0"] else "-"
        p20_str = f"{r['p20']:.2f}" if r["p20"] else "-"
        ret_str = f"{r['ret']:+.1f}%" if r["ret"] is not None else "-"
        print(
            f"{r['ticker']:<8} {r['score']:>6.1f} {r['insiders']:>4} "
            f"{str(r['detected']):>12} {p0_str:>10} {p20_str:>10} {ret_str:>8}  {r['status']}"
        )

    done = [r for r in results if r["ret"] is not None]
    if done:
        positive = [r for r in done if r["ret"] >= 0]
        avg_ret  = sum(r["ret"] for r in done) / len(done)
        hit_rate = len(positive) / len(done) * 100
        print()
        print(f"Ozet: {len(done)} olcum | Ortalama getiri: {avg_ret:+.1f}% | Hit rate (yukselen): {hit_rate:.0f}%")
        print("Base rate beklentisi (random): ~50% yukselis, ~0% ortalama getiri")


async def main() -> None:
    clusters = await _get_clusters()
    results = _check_returns(clusters)
    _print_table(results)


if __name__ == "__main__":
    asyncio.run(main())
