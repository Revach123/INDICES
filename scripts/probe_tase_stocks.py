"""אימות טיקרים נוספים ל-TASE (בזן, הבורסה עצמה, פניקס-פנק) שנמצאו דרך
ה-API הרשמי של TASE (AssetName) - צריך את הטיקר של Yahoo שמתאים.

הרצה: python scripts/probe_tase_stocks.py
"""
import json
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)

CANDIDATES = {
    "ORL.TA": "בזן (Bazan Oil Refineries) - מ-WebSearch",
    "TASE.TA": "הבורסה לני\"ע בתל אביב (TASE עצמה) - מ-WebSearch",
}


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    report = {}
    for symbol, expected in CANDIDATES.items():
        try:
            r = session.get(CHART_URL.format(symbol=symbol), params={"range": "5d", "interval": "1d"}, timeout=15)
            data = r.json()
            result = (data.get("chart") or {}).get("result")
            if not result:
                report[symbol] = {"expected": expected, "error": "no result"}
                continue
            meta = result[0].get("meta", {})
            report[symbol] = {
                "expected": expected,
                "instrumentType": meta.get("instrumentType"),
                "longName": meta.get("longName") or meta.get("shortName"),
                "price": meta.get("regularMarketPrice"),
            }
        except Exception as e:
            report[symbol] = {"expected": expected, "error": repr(e)}

    txt = json.dumps(report, ensure_ascii=False, indent=2)
    print(txt)
    (OUT / "tase_stocks.json").write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
