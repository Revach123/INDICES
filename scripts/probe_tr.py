"""בדיקת היתכנות: איתור מקורות Total-Return אמיתיים (לא רק Price) ב-Yahoo
Finance, למדדים שכרגע ממופים לפרוקסי לא-מדויק (ETF מחלק דיבידנד / מדד מחיר
בלי דיבידנדים) - ר' דיון על פער TR-מול-Price ב-swap_ticker_map.csv.

שתי אסטרטגיות מועמדים לכל מדד:
1. טיקר TR ישיר (אם Yahoo בכלל מפרסם, כמו ^SP500TR שכבר עובד).
2. ETF "מצטבר" (Accumulating, לא Distributing) - ETF כזה לא מחלק דיבידנד
   אלא צובר אותו ב-NAV, ולכן ה-NAV/מחיר שלו עוקב אחרי TR (לא Price) של
   המדד שהוא עוקב - פרוקסי טוב בהרבה מ-ETF מחלק.

הרצה: python scripts/probe_tr.py
"""
import json
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)

# index_id -> רשימת טיקרים מועמדים (סדר עדיפות: TR ישיר קודם, אח"כ ETF מצטבר)
CANDIDATES = {
    "nasdaq100_tr": ["^NDXTR", "^NDXT", "CNDX.L", "SXRV.DE", "EQQQ.L"],
    "stoxx50_tr": ["^SX5T", "^SX5TR", "EXW1.DE", "CSX5.MI", "C50.PA"],
    "ftse100_tr": ["^FTSETR", "^UKXTR", "ISF.L", "CUKX.L"],
    "ftsemib_tr": ["^FTSEMIBTR", "^FTMIBTR", "SPMIB.MI", "LYXBIT.MI", "XMIB.MI"],
    "russell2000_tr": ["^RUTTR", "^RU20INTR", "IUSN.DE", "WSML.L"],
    "nikkei_tr": ["^N225TR", "^NKYTR", "1329.T", "1320.T"],
    "topix_tr": ["^TPXTR", "1475.T", "1348.T"],
    "dax_check": ["^GDAXI"],  # בדיקת שפיות: DAX כבר TR מטבעו, לא אמור להיות פער
}


def try_symbol(session, symbol):
    try:
        r = session.get(CHART_URL.format(symbol=symbol),
                         params={"range": "1mo", "interval": "1d"}, timeout=15)
        if r.status_code != 200:
            return {"status": r.status_code}
        data = r.json()
        result = (data.get("chart") or {}).get("result")
        if not result:
            return {"status": 200, "error": (data.get("chart") or {}).get("error")}
        meta = result[0].get("meta", {})
        closes = (result[0].get("indicators") or {}).get("quote", [{}])[0].get("close") or []
        closes = [c for c in closes if c is not None]
        return {
            "status": 200, "ok": True,
            "currency": meta.get("currency"), "instrumentType": meta.get("instrumentType"),
            "exchangeName": meta.get("exchangeName"), "longName": meta.get("longName"),
            "last_close": closes[-1] if closes else None,
        }
    except Exception as e:
        return {"error": repr(e)}


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    report = {}
    for index_id, symbols in CANDIDATES.items():
        report[index_id] = {}
        for sym in symbols:
            report[index_id][sym] = try_symbol(session, sym)
    txt = json.dumps(report, ensure_ascii=False, indent=2)
    print(txt)
    (OUT / "tr_report.json").write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
