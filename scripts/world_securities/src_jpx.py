"""יפן - JPX (הבורסה של טוקיו). מקורות רשמיים:
  data_e.xlsx  - "List of TSE-listed Issues": קוד, שם, שוק/מוצר (Prime/Standard/Growth, ETFs/ETNs,
                 REITs...), ענף (33/17 ענפי TSE), קבוצת גודל TOPIX. מתעדכן חודשית.
  דף ה-ETN     - רשימת ה-ETN הרשומים (להפרדה בין ETF ל-ETN שבקובץ הראשי מאוחדים).
אין ISIN בקבצי JPX; ה-FIGI מ-OpenFIGI לפי הקוד ב-XTKS, וה-ISIN מושלם במאגר Revach
מאחזקות הקרנות (ISIN -> OpenFIGI -> אותו FIGI).
"""
import io
import re
from urllib.parse import urljoin

from common import get, log

PAGE = "https://www.jpx.co.jp/english/markets/statistics-equities/misc/01.html"
ETN_PAGE = "https://www.jpx.co.jp/english/equities/products/etns/issues/01.html"

# "Section/Products" -> (type, type_he). ערך שלא מופיע כאן נשמר כמו שהוא ומסומן Other.
SECTION_TYPES = [
    (r"^ETFs?/ ?ETNs?", ("ETF", "קרן סל (ETF)")),
    (r"^REIT", ("REIT", "קרן ריט (REIT)")),
    (r"Infrastructure", ("Infrastructure Fund", "קרן תשתיות")),
    (r"^(Prime|Standard|Growth) Market", ("Common Stock", "מניה רגילה")),
    (r"PRO Market", ("Common Stock", "מניה רגילה")),
    (r"Preferred", ("Preferred Stock", "מניית בכורה")),
]


def build():
    import pandas as pd
    page = get(PAGE).text
    links = [urljoin(PAGE, h) for h in re.findall(r'href="([^"]+data_e\.xlsx?)"', page)]
    if not links:
        raise RuntimeError("jpx: listed-issues file link not found")
    df = pd.read_excel(io.BytesIO(get(links[0]).content), dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]
    etn_codes = set(re.findall(r">\s*(\d{3}[0-9A-Z])\s*<", get(ETN_PAGE).text))
    log(f"jpx: {len(df)} issues, {len(etn_codes)} ETN codes; columns {list(df.columns)}")
    if len(df) < 3000:
        raise RuntimeError(f"jpx: only {len(df)} rows")
    out, sections = [], {}
    for _, r in df.iterrows():
        code = str(r.get("Local Code", "")).strip()
        if not code:
            continue
        sec = str(r.get("Section/Products", "")).strip()
        sections[sec] = sections.get(sec, 0) + 1
        typ = next((t for rx, t in SECTION_TYPES if re.search(rx, sec, re.I)), ("Other", "אחר"))
        if typ[0] == "ETF" and code in etn_codes:
            typ = ("ETN", "תעודת סל (ETN)")
        foreign = "Foreign" in sec

        def clean(v):
            v = str(v or "").strip()
            return None if v in ("", "-") else v

        eff = clean(r.get("Effective Date"))
        out.append({
            "id": f"XTKS:{code}", "isin": None, "market": "JP", "region": "JP", "country": "JP",
            "name": clean(r.get("Name (English)")), "security_type": typ[0], "security_type_he": typ[1],
            "type_source": "jpx_section" + ("+etn_list" if typ[0] == "ETN" else ""),
            "exchange_segment": sec, "foreign_issuer": 1 if foreign else 0,
            "sector": clean(r.get("33 Sector(name)")), "sector_code": clean(r.get("33 Sector(Code)")),
            "sector17": clean(r.get("17 Sector(name)")), "size_group": clean(r.get("Size (New Index Series)")),
            "currency": "JPY", "primary_mic": "XTKS", "primary_oprt": "XJPX", "primary_source": "exchange",
            "listings": [{"m": "XTKS", "o": "XJPX", "cc": "JP", "cat": "RMKT", "r": "JPX"}],
            "listing_countries": ["JP"],
            "ticker": code, "tickers": [code], "ticker_source": "exchange",
            "source_file_date": f"{eff[:4]}-{eff[4:6]}-{eff[6:8]}" if eff and len(eff) == 8 else None,
        })
    log(f"jpx: sections {sections}")
    return out
