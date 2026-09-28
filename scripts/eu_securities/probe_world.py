"""בדיקת היתכנות - מקורות רשמיים לשווייץ (SIX), יפן (JPX) וקנדה (TMX), ו-OpenFIGI לפי MIC.
כותב probe_out/world_*.json. הרצה: python scripts/eu_securities/probe_world.py
"""
import io
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)
S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"})
REPORT = {}


def fetch(name, url, keep=False, **kw):
    t = time.monotonic()
    try:
        r = S.get(url, timeout=90, **kw)
        info = {"url": url, "status": r.status_code, "bytes": len(r.content), "sec": round(time.monotonic() - t, 1),
                "ctype": r.headers.get("content-type"), "final_url": r.url}
        ct = (r.headers.get("content-type") or "").lower()
        if any(x in ct for x in ("json", "text", "csv", "xml", "html")):
            info["head"] = r.text[:1500]
        REPORT[name] = info
        return r if keep else None
    except Exception as e:  # noqa: BLE001
        REPORT[name] = {"url": url, "error": repr(e)}
        return None


def links(name, url, pattern):
    r = fetch(name, url, keep=True)
    if r is None or not r.ok:
        return []
    found = sorted({urljoin(r.url, h) for h in re.findall(r'href="([^"]+)"', r.text) if re.search(pattern, h, re.I)})
    REPORT[name]["links"] = found[:80]
    return found


def excel_summary(name, url):
    r = fetch(name, url, keep=True)
    if r is None or not r.ok:
        return
    try:
        import pandas as pd
        sheets = pd.read_excel(io.BytesIO(r.content), sheet_name=None, header=None)
        REPORT[name]["sheets"] = {k: {"shape": list(v.shape), "head": v.head(12).astype(str).values.tolist()}
                                  for k, v in sheets.items()}
    except Exception as e:  # noqa: BLE001
        REPORT[name]["excel_error"] = repr(e)


def main():
    # ---- SIX (שווייץ)
    fetch("six_equity_issuers_csv", "https://www.six-group.com/sheldon/equity_issuers/v1/equity_issuers.csv")
    fetch("six_equity_issuers_json", "https://www.six-group.com/sheldon/equity_issuers/v1/equity_issuers.json")
    fetch("six_fqs_shares", "https://www.six-group.com/fqs/ref.csv?select=ShortName,ValorSymbol,ValorNumber,ISIN,"
          "TradingBaseCurrency,IssuerNameFull,SecTypeCode,PortalSegment,ProductLine&where=PortalSegment=EQ*"
          "&orderby=ShortName&page=1&pagesize=99999")
    fetch("six_fqs_funds", "https://www.six-group.com/fqs/ref.csv?select=ShortName,ValorSymbol,ISIN,PortalSegment"
          "&where=PortalSegment=FU*&page=1&pagesize=99999")
    fetch("six_fqs_all_json", "https://www.six-group.com/fqs/ref.json?select=ISIN,ValorSymbol,ShortName,PortalSegment"
          "&where=PortalSegment=EQ&page=1&pagesize=50")
    links("six_shares_page", "https://www.six-group.com/en/market-data/shares/companies.html",
          r"(csv|xls|json|download|sheldon|fqs)")
    links("six_etf_page", "https://www.six-group.com/en/market-data/etf/etf-explorer.html",
          r"(csv|xls|json|download|sheldon|fqs)")

    # ---- JPX (יפן)
    for u in links("jpx_listed_page_en", "https://www.jpx.co.jp/english/markets/statistics-equities/misc/01.html",
                   r"\.xlsx?$"):
        excel_summary("jpx_listed_xls", u)
        break
    links("jpx_listed_page_ja", "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html", r"\.xlsx?$")
    links("jpx_sicc_page", "https://www.jpx.co.jp/sicc/", r"(isin|code|csv|zip|xls)")
    links("jpx_sicc_en", "https://www.jpx.co.jp/english/sicc/", r"(isin|code|csv|zip|xls)")
    links("jpx_etf_page", "https://www.jpx.co.jp/english/equities/products/etfs/issues/01.html", r"\.(xlsx?|csv|pdf)$")

    # ---- TMX (קנדה)
    fetch("tmx_directory_tsx", "https://www.tsx.com/json/company-directory/search/tsx/%5E*")
    fetch("tmx_directory_tsxv", "https://www.tsx.com/json/company-directory/search/tsxv/%5E*")
    fetch("tmx_interlisted", "https://www.tsx.com/files/trading/interlisted-companies.txt")
    for u in links("tmx_mig_page", "https://www.tsx.com/en/listings/current-market-statistics", r"\.xlsx?"):
        if re.search(r"(listed|issuer|compan)", u, re.I):
            excel_summary("tmx_mig_xlsx", u)
            break
    fetch("tmx_mig_page2", "https://www.tsx.com/listings/current-market-statistics/mig-archives")

    # ---- OpenFIGI לפי MIC (בלי מפתח)
    jobs = [{"idType": "ID_ISIN", "idValue": "FR0000121014", "micCode": "XPAR"},
            {"idType": "ID_ISIN", "idValue": "DE0007164600", "micCode": "XETR"},
            {"idType": "ID_ISIN", "idValue": "IE00B5BMR087", "micCode": "XLON"},
            {"idType": "TICKER", "idValue": "7203", "micCode": "XTKS"},
            {"idType": "TICKER", "idValue": "7203", "exchCode": "JT"},
            {"idType": "ID_ISIN", "idValue": "JP3633400001", "micCode": "XTKS"},
            {"idType": "TICKER", "idValue": "RY", "micCode": "XTSE"},
            {"idType": "TICKER", "idValue": "BBD/B", "micCode": "XTSE"},
            {"idType": "ID_ISIN", "idValue": "CA7800871021", "micCode": "XTSE"},
            {"idType": "ID_ISIN", "idValue": "CH0038863350", "micCode": "XSWX"}]
    try:
        r = S.post("https://api.openfigi.com/v3/mapping", json=jobs, timeout=60)
        REPORT["openfigi_mic"] = {"status": r.status_code, "jobs": jobs,
                                  "result": r.json() if r.ok else r.text[:500]}
    except Exception as e:  # noqa: BLE001
        REPORT["openfigi_mic"] = {"error": repr(e)}

    txt = json.dumps(REPORT, ensure_ascii=False, indent=1, default=str)
    (OUT / "world_probe_report.json").write_text(txt, encoding="utf-8")
    print(txt[:30000])


if __name__ == "__main__":
    main()
