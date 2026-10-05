"""בודק את yahoo_candidates ב-data/index_registry.csv - מדדים שעדיין אין להם
סדרת מחיר ב-universe. מועמד נחשב תקין רק אם Yahoo מחזיר instrumentType == INDEX
(ר' README, "כלל קריטי": ETF אינו תחליף חוקי למדד). את רמת המחיר
(regularMarketPrice) יש להשוות ידנית לרמת המדד הידועה לפני הוספה ל-universe.csv.

הרצה: python scripts/probe_registry_candidates.py
"""
import csv
import json
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
REGISTRY = Path("data/index_registry.csv")
OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    with REGISTRY.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    report = {}
    for row in rows:
        for symbol in filter(None, (s.strip() for s in row["yahoo_candidates"].split("|"))):
            key = f'{row["index_key"]}:{symbol}'
            try:
                r = session.get(CHART_URL.format(symbol=symbol),
                                params={"range": "5d", "interval": "1d"}, timeout=15)
                result = ((r.json().get("chart") or {}).get("result")) or []
                if not result:
                    report[key] = {"http": r.status_code, "error": "no result"}
                    continue
                meta = result[0].get("meta", {})
                report[key] = {
                    "bbg_ticker": row["bbg_ticker"],
                    "instrumentType": meta.get("instrumentType"),
                    "regularMarketPrice": meta.get("regularMarketPrice"),
                    "currency": meta.get("currency"),
                    "longName": meta.get("longName") or meta.get("shortName"),
                    "firstTradeDate": meta.get("firstTradeDate"),
                }
            except Exception as e:
                report[key] = {"error": repr(e)}

    txt = json.dumps(report, ensure_ascii=False, indent=2)
    print(txt)
    (OUT / "registry_candidates.json").write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
