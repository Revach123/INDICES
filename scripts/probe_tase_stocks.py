"""אימות טיקרים בודדים ל-TASE (בנקים/מבטחות גדולים שמופיעים באופציות
MASLULIM בשם עברי מלא) מול Yahoo Finance - כדי לא להציב טיקר מהזיכרון בלי
אימות (אותו עיקרון כמו probe_instrument_types.py).

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
    "POLI.TA": "בנק הפועלים (Bank Hapoalim)",
    "LUMI.TA": "בנק לאומי (Bank Leumi)",
    "DSCT.TA": "בנק דיסקונט (Discount Bank)",
    "MZTF.TA": "מזרחי טפחות (Mizrahi-Tefahot)",
    "BEZQ.TA": "בזק (Bezeq)",
    "CLIS.TA": "כלל ביטוח (Clal Insurance)",
    "PHOE.TA": "הפניקס (Phoenix)",
    "PHOE1.TA": "הפניקס (Phoenix) - variant",
    "MMHD.TA": "מנורה מבטחים (Menora Mivtachim)",
    "MGDL.TA": "מגדל ביטוח (Migdal Insurance)",
    "ENLT.TA": "אנלייט (Enlight Renewable Energy)",
    "AFHL.TA": "אפקון החזקות (Afcon Holdings)",
    "DMRI.TA": "דמרי (Dmri Group)",
    "HYSH.TA": "הכשרת הישוב (Hachsharat Hayishuv)",
    "BAZN.TA": "בזן (Bazan / Oil Refineries)",
    "PZOL.TA": "פז (Paz Oil)",
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
