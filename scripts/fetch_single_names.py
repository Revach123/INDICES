"""מושך היסטוריית מחירים (OHLC יומי, כל הטווח הזמין) לטיקרים בודדים (מניות/
ETF-ים ספציפיים, לא מדדים) שמשמשים כנכס-בסיס לאופציות בדוחות MASLULIM.
נפרד מ-fetch_prices.py (data/universe.csv) בכוונה: זו רשימה פתוחה שגדלה
לפי מה שבפועל מופיע בדוחות (נכון להיום ~70 טיקרים, לא מאגר מתוקנן), לא
כדאי לערבב עם ה-universe.csv המתוקנן של ~50 המדדים המובילים.

מקור הרשימה: scripts/funds_holdings/swap_index_pricing.py-style parsing
ב-MASLULIM (option_ticker_parse.py, לא נכלל בריפו הזה) - סריקת "שם נייר
ערך" בגיליונות אופציות/לא סחיר אופציות, מסוננת ל-נכס בסיס==מניות. עודכן
ידנית ב-data/option_underlyers.txt כשמתגלים טיקרים חדשים.

הרצה: python scripts/fetch_single_names.py
"""
import csv
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
TICKER_LIST = Path("data/option_underlyers.txt")
OUT_DIR = Path("data/prices/singles")
# period1/period2 מפורשים, לא range=max/2y - אומת (probe_daily_granularity.py)
# ש-range מחזיר בפועל נתונים רבעוניים לטווחים ארוכים למרות interval=1d;
# period מפורש כן מחזיר יומי אמיתי. מכסה את כל טווח הארכיון של MASLULIM.
PERIOD1 = int(datetime(2023, 6, 1, tzinfo=timezone.utc).timestamp())
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


def load_tickers() -> list[str]:
    with TICKER_LIST.open(encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def safe_filename(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", symbol)


def fetch_one(session: requests.Session, symbol: str) -> list[dict]:
    r = session.get(CHART_URL.format(symbol=symbol),
                     params={"period1": PERIOD1, "period2": int(time.time()),
                              "interval": "1d", "events": "history"},
                     timeout=30)
    r.raise_for_status()
    data = r.json()
    result = (data.get("chart") or {}).get("result")
    if not result:
        err = (data.get("chart") or {}).get("error")
        raise RuntimeError(f"no result (error={err})")
    res = result[0]
    ts = res.get("timestamp") or []
    quote = (res.get("indicators") or {}).get("quote", [{}])[0]
    closes = quote.get("close") or []
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    vols = quote.get("volume") or []
    rows = []
    for i, t in enumerate(ts):
        close = closes[i] if i < len(closes) else None
        if close is None:
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat()
        rows.append({
            "date": d,
            "open": opens[i] if i < len(opens) else "",
            "high": highs[i] if i < len(highs) else "",
            "low": lows[i] if i < len(lows) else "",
            "close": close,
            "volume": vols[i] if i < len(vols) else "",
        })
    return rows


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tickers = load_tickers()
    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    ok, failed = [], []
    for symbol in tickers:
        try:
            bars = fetch_one(session, symbol)
            if not bars:
                raise RuntimeError("0 bars returned")
            out_path = OUT_DIR / f"{safe_filename(symbol)}.csv"
            with out_path.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["date", "open", "high", "low", "close", "volume"])
                w.writeheader()
                w.writerows(bars)
            ok.append(symbol)
            print(f"OK   {symbol:<12}{len(bars):>6} rows  {bars[0]['date']} -> {bars[-1]['date']}")
        except Exception as e:
            failed.append((symbol, repr(e)))
            print(f"FAIL {symbol:<12}{e!r}")
        time.sleep(0.3)

    print(f"\n{len(ok)} ok, {len(failed)} failed")
    if failed:
        print("Failed:", ", ".join(f"{s}({e})" for s, e in failed))


if __name__ == "__main__":
    main()
