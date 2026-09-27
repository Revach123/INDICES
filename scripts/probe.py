"""בדיקת היתכנות: אילו מקורות נתונים חינמיים למדדים (מחירים היסטוריים/עדכניים
+ הרכבי מדדים) נגישים מ-GitHub Actions. ריצה חד-פעמית לפני בניית הפייפליין
האמיתי - כדי לא לבנות סקריפטים מול מקור שממילא חסום.

הרצה: python scripts/probe.py
"""
import json
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)

CANDIDATES = {
    "yahoo_chart_spx": "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=5d&interval=1d",
    "stooq_spx": "https://stooq.com/q/d/l/?s=%5Espx&i=d",
    "stooq_ta125": "https://stooq.com/q/d/l/?s=%5Etel_all&i=d",
    "fred_sp500": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500",
    "wikipedia_sp500_constituents": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "ishares_ivv_holdings": "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/1467271812596.ajax?fileType=csv&fileName=IVV_holdings&dataType=fund",
    "tase_indices": "https://api.tase.co.il/api/index/basicindexlist",
    "worldbank": "https://api.worldbank.org/v2/country?format=json",
    "ecb_sdw": "https://sdw-wsrest.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A",
    "nasdaqtrader": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "msci_index_perf": "https://www.msci.com/end-of-day-data-search",
    "investing_ping": "https://www.investing.com",
    "google_ping": "https://www.google.com",
    "sec_ping": "https://www.sec.gov",
}


def main():
    report = {}
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    for name, url in CANDIDATES.items():
        try:
            r = s.get(url, timeout=20)
            report[name] = {
                "status": r.status_code,
                "bytes": len(r.content),
                "content_type": r.headers.get("content-type"),
                "head": r.text[:200] if "json" in (r.headers.get("content-type") or "") or "csv" in url or "text" in (r.headers.get("content-type") or "") else None,
            }
        except Exception as e:
            report[name] = {"error": repr(e)}
    txt = json.dumps(report, ensure_ascii=False, indent=2)
    print(txt)
    (OUT / "report.json").write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
