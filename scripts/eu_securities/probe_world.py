"""בדיקת היתכנות (סבב 2) - פרטים משלימים: סוגי ניירות ב-SIX, ISIN ביפן (SICC), ETN ביפן,
וקובץ המנפיקים הרשמי של TMX (MiG). כותב probe_out/world_*.json.
"""
import collections
import csv
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


def fetch(name, url, **kw):
    t = time.monotonic()
    try:
        r = S.get(url, timeout=90, **kw)
        REPORT[name] = {"url": url, "status": r.status_code, "bytes": len(r.content),
                        "sec": round(time.monotonic() - t, 1), "ctype": r.headers.get("content-type")}
        return r
    except Exception as e:  # noqa: BLE001
        REPORT[name] = {"url": url, "error": repr(e)}
        return None


def hrefs(name, url, pattern):
    r = fetch(name, url)
    if r is None or not r.ok:
        return []
    found = sorted({urljoin(r.url, h) for h in re.findall(r'href="([^"]+)"', r.text) if re.search(pattern, h, re.I)})
    REPORT[name]["links"] = found[:150]
    return found


def excel(name, url, rows=15):
    r = fetch(name, url)
    if r is None or not r.ok:
        return
    try:
        import pandas as pd
        sheets = pd.read_excel(io.BytesIO(r.content), sheet_name=None, header=None)
        REPORT[name]["sheets"] = {k: {"shape": list(v.shape), "head": v.head(rows).astype(str).values.tolist()}
                                  for k, v in sheets.items()}
    except Exception as e:  # noqa: BLE001
        REPORT[name]["excel_error"] = repr(e)
        REPORT[name]["head"] = r.content[:300].decode("latin-1")


SIX_FIELDS = ("ShortName,ValorSymbol,ValorNumber,ISIN,TradingBaseCurrency,IssuerNameFull,SecTypeCode,"
              "SecTypeDesc,PortalSegment,ProductLine,ListingSegment,MarketSegment,ETFType,UnderlyingIndex,"
              "IssuerCountryCode,FundDomicile,IndexName,AssetClassDesc,ProductType")


def six():
    for seg in ("EQ", "FU", "ET", "EP", "FU*", "ET*"):
        r = fetch(f"six_{seg}", f"https://www.six-group.com/fqs/ref.csv?select={SIX_FIELDS}"
                                f"&where=PortalSegment={seg}&page=1&pagesize=99999")
        if r is None or not r.ok:
            continue
        txt = r.content.decode("iso-8859-1")
        REPORT[f"six_{seg}"]["head"] = txt[:1200]
        rows = list(csv.DictReader(io.StringIO(txt), delimiter=";"))
        REPORT[f"six_{seg}"]["n"] = len(rows)
        for col in ("SecTypeCode", "SecTypeDesc", "PortalSegment", "ProductLine", "ListingSegment", "MarketSegment",
                    "ETFType", "AssetClassDesc", "ProductType"):
            if rows and col in rows[0]:
                REPORT[f"six_{seg}"][f"distinct_{col}"] = collections.Counter(x.get(col) for x in rows).most_common(40)
    # כל הסגמנטים: בקשה ממוינת קטנה עם where ריק
    r = fetch("six_any", "https://www.six-group.com/fqs/ref.csv?select=PortalSegment&page=1&pagesize=200000")
    if r is not None and r.ok:
        rows = r.content.decode("iso-8859-1").splitlines()[1:]
        REPORT["six_any"]["segments"] = collections.Counter(rows).most_common(50)


def jpx():
    for u in hrefs("jpx_sicc_code_index", "https://www.jpx.co.jp/english/sicc/securities-code/index.html",
                   r"(\.(csv|zip|xlsx?|txt)$|isin|download)"):
        REPORT.setdefault("jpx_sicc_files", []).append(u)
    for p in ("01", "02"):
        hrefs(f"jpx_sicc_{p}", f"https://www.jpx.co.jp/english/sicc/securities-code/{p}.html",
              r"(\.(csv|zip|xlsx?|txt)$|isin|download)")
        hrefs(f"jpx_sicc_ja_{p}", f"https://www.jpx.co.jp/sicc/securities-code/{p}.html",
              r"(\.(csv|zip|xlsx?|txt)$|isin|download)")
    hrefs("jpx_etn_page", "https://www.jpx.co.jp/english/equities/products/etns/issues/01.html",
          r"\.(xlsx?|csv|pdf)$")
    r = fetch("jpx_etn_html", "https://www.jpx.co.jp/english/equities/products/etns/issues/01.html")
    if r is not None and r.ok:
        REPORT["jpx_etn_html"]["codes"] = sorted(set(re.findall(r">\s*(\d{3}[0-9A-Z])\s*<", r.text)))[:200]
    hrefs("jpx_reit_page", "https://www.jpx.co.jp/english/equities/products/reits/issues/index.html",
          r"\.(xlsx?|csv)$")
    hrefs("jpx_pro_page", "https://www.jpx.co.jp/english/equities/products/tpm/issues/index.html", r"\.(xlsx?|csv)$")


def tmx():
    for u in hrefs("tmx_mig_current", "https://www.tsx.com/en/listings/current-market-statistics",
                   r"(xlsx?|resource|mig|download)"):
        if re.search(r"xlsx?", u, re.I) and re.search(r"(listed|issuer|compan)", u, re.I):
            excel("tmx_mig_xlsx", u, rows=12)
            break
    hrefs("tmx_mig_archives", "https://www.tsx.com/en/listings/current-market-statistics/mig-archives",
          r"(xlsx?|resource|mig|download)")
    r = fetch("tmx_etf_directory", "https://www.tsx.com/json/company-directory/search/tsx/%5E*?type=etf")
    if r is not None and r.ok:
        REPORT["tmx_etf_directory"]["head"] = r.text[:600]


def main():
    for f in (six, jpx, tmx):
        try:
            f()
        except Exception as e:  # noqa: BLE001
            REPORT[f"{f.__name__}_error"] = repr(e)
    txt = json.dumps(REPORT, ensure_ascii=False, indent=1, default=str)
    (OUT / "world_probe2_report.json").write_text(txt, encoding="utf-8")
    print(txt[:30000])


if __name__ == "__main__":
    main()
