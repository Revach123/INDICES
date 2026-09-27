"""מושך היסטוריית מחירים (OHLC יומי, כל הטווח הזמין) לכל מדד ב-data/universe.csv
דרך Yahoo Finance chart API - המקור היחיד שנמצא נגיש ואמין מ-GitHub Actions
(ר' probe.py: stooq/TASE/investing חסומים ע"י הגנת בוט, SEC דורש User-Agent
עם אימייל, ECB/FRED לא נגישים). כותב/מחליף קובץ CSV מלא לכל מדד ב-data/prices/
- לא incremental - טווח 'max' של Yahoo זול מספיק (בקשת JSON אחת) שאין טעם
לסבך עם עדכון חלקי, וזה גם מתקן את עצמו אוטומטית אם Yahoo מתקן נתון היסטורי.

הרצה: python scripts/fetch_prices.py
"""
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
UNIVERSE = Path("data/universe.csv")
OUT_DIR = Path("data/prices")
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


def load_universe() -> list[dict]:
    with UNIVERSE.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fetch_one(session: requests.Session, symbol: str) -> list[dict]:
    r = session.get(CHART_URL.format(symbol=symbol),
                     params={"range": "max", "interval": "1d", "events": "history"},
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
    universe = load_universe()
    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    ok, failed = [], []
    for row in universe:
        index_id, symbol_field = row["index_id"], row["yahoo_symbol"]
        # מאפשר כמה טיקרים מועמדים מופרדים ב-"|" בעמודת yahoo_symbol - מנסים
        # לפי הסדר, עוצרים בראשון שמצליח. חוסך סבב CI נפרד לכל ניחוש כושל
        # (נמצא בפועל: TA125.TA/^TA125 שניהם נכשלו על TA-125, לא ברור מראש
        # איזו מוסכמה Yahoo באמת משתמש בה למדדים ישראליים ספציפיים אלה).
        candidates = [s.strip() for s in symbol_field.split("|") if s.strip()]
        bars = None
        used_symbol = None
        errors = []
        for symbol in candidates:
            try:
                bars = fetch_one(session, symbol)
                if not bars:
                    raise RuntimeError("0 bars returned")
                used_symbol = symbol
                break
            except Exception as e:
                errors.append(f"{symbol}: {e!r}")
            time.sleep(0.3)

        if bars:
            out_path = OUT_DIR / f"{index_id}.csv"
            with out_path.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["date", "open", "high", "low", "close", "volume"])
                w.writeheader()
                w.writerows(bars)
            ok.append((index_id, used_symbol, len(bars), bars[0]["date"], bars[-1]["date"]))
            print(f"OK   {index_id:<20}{used_symbol:<14}{len(bars):>6} rows  {bars[0]['date']} -> {bars[-1]['date']}")
        else:
            failed.append((index_id, symbol_field, errors))
            print(f"FAIL {index_id:<20}{symbol_field:<14}{' | '.join(errors)}")

    print(f"\n{len(ok)} ok, {len(failed)} failed")
    if failed:
        print("Failed symbols:", ", ".join(f"{i}({s})" for i, s, _ in failed))


if __name__ == "__main__":
    main()
