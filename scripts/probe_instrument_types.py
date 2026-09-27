"""ביקורת בטיחות: לכל index_id ב-data/universe.csv, בודק אם הטיקר שלו הוא
INDEX אמיתי (בטוח להצבה בנוסחת יחידות×מחיר מול "שער נכס הבסיס" שדוחות
סוואפ מדווחים) או ETF/מכשיר אחר (מסוכן - קנה-מידה שרירותי, לא רמת המדד -
ר' README, סעיף "כלל קריטי"). נמצא בפועל: CNDX.L/C50.PA (ETF-ים) גרמו
להרעת MAE כשהוצבו בנוסחה, בעוד ^RUTTR (INDEX אמיתי) לא.

הרצה: python scripts/probe_instrument_types.py
"""
import csv
import json
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
UNIVERSE = Path("data/universe.csv")
OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    with UNIVERSE.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    report = {}
    for row in rows:
        index_id = row["index_id"]
        symbol = row["yahoo_symbol"].split("|")[0].strip()
        try:
            r = session.get(CHART_URL.format(symbol=symbol),
                             params={"range": "5d", "interval": "1d"}, timeout=15)
            data = r.json()
            result = (data.get("chart") or {}).get("result")
            if not result:
                report[index_id] = {"symbol": symbol, "error": "no result"}
                continue
            meta = result[0].get("meta", {})
            report[index_id] = {
                "symbol": symbol,
                "instrumentType": meta.get("instrumentType"),
                "regularMarketPrice": meta.get("regularMarketPrice"),
                "longName": meta.get("longName") or meta.get("shortName"),
            }
        except Exception as e:
            report[index_id] = {"symbol": symbol, "error": repr(e)}

    txt = json.dumps(report, ensure_ascii=False, indent=2)
    print(txt)
    (OUT / "instrument_types.json").write_text(txt, encoding="utf-8")

    non_index = {k: v for k, v in report.items() if v.get("instrumentType") not in ("INDEX",)}
    print(f"\n{len(non_index)}/{len(report)} לא מסוג INDEX:")
    for k, v in non_index.items():
        print(f"  {k:<20}{v.get('symbol'):<12}{v.get('instrumentType')}\t{v.get('longName')}")


if __name__ == "__main__":
    main()
