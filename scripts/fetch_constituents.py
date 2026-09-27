"""מושך הרכבי מדדים (רשימת חברות מרכיבות) מוויקיפדיה - המקור היחיד שנמצא נגיש
מ-Actions לנתון הזה (ר' probe.py: iShares CSV endpoint שגוי/חסום, TASE חסום).
עובד רק על מדדים שיש להם wikipedia_url ב-universe.csv; מדדים ללא מקור ציבורי
(כמו אינדקסים סינתטיים של בנקים - GSC1000N/JPMTVEUI וכד') נשארים ללא הרכב -
זה מגבלה אמיתית של המקורות הפתוחים, לא באג.

היוריסטיקה: לוקחים מתוך כל הטבלאות בעמוד את הטבלה עם הכי הרבה שורות מתוך
אלו שיש להן עמודה בשם התואם ל"Symbol"/"Ticker"/"סימול" - נכון לרוב עמודי
ה-"List of X companies"/"מדד Y" בוויקיפדיה, אבל שביר לשינויי מבנה עמוד.

הרצה: python scripts/fetch_constituents.py
"""
import csv
import io
import time
from pathlib import Path

import pandas as pd
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
UNIVERSE = Path("data/universe.csv")
OUT_DIR = Path("data/constituents")
SYMBOL_COL_HINTS = ("symbol", "ticker", "סימול", "קוד")


def load_universe() -> list[dict]:
    with UNIVERSE.open(encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("wikipedia_url")]


def pick_constituents_table(html: str) -> pd.DataFrame | None:
    tables = pd.read_html(io.StringIO(html))
    candidates = []
    for t in tables:
        cols_lower = [str(c).strip().lower() for c in t.columns]
        if any(any(hint in c for hint in SYMBOL_COL_HINTS) for c in cols_lower):
            candidates.append(t)
    if not candidates:
        return None
    return max(candidates, key=len)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    universe = load_universe()
    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    ok, failed = [], []
    for row in universe:
        index_id, url = row["index_id"], row["wikipedia_url"]
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            table = pick_constituents_table(r.text)
            if table is None or len(table) < 3:
                raise RuntimeError(f"no plausible constituents table found ({len(table) if table is not None else 0} rows)")
            out_path = OUT_DIR / f"{index_id}.csv"
            table.to_csv(out_path, index=False, encoding="utf-8")
            ok.append((index_id, len(table)))
            print(f"OK   {index_id:<20}{len(table):>5} rows -> {out_path}")
        except Exception as e:
            failed.append((index_id, repr(e)))
            print(f"FAIL {index_id:<20}{e!r}")
        time.sleep(0.5)

    print(f"\n{len(ok)} ok, {len(failed)} failed")


if __name__ == "__main__":
    main()
