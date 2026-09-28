"""קנדה - TMX (Toronto Stock Exchange + TSX Venture). מקורות רשמיים:
  company-directory  - כל החברות הרשומות וכל קווי המסחר (instruments) שלהן, ב-TSX וב-TSXV
  interlisted        - רשימת החברות הרשומות גם בחו"ל, עם הסימול בארה"ב והבורסה

סוג: לפי OpenFIGI (Bloomberg) כשהנייר זוהה; אחרת לפי הסימבולוגיה הרשמית של TMX
(.PR = בכורה, .WT = כתב אופציה, .DB = אג"ח להמרה, .RT = זכויות, .NT = שטר). אין ISIN במקורות;
ה-ISIN מושלם במאגר Revach מאחזקות הקרנות דרך ה-FIGI.
"""
import re

from common import get, log

DIRECTORY = "https://www.tsx.com/json/company-directory/search/{board}/%5E*"
INTERLISTED = "https://www.tsx.com/files/trading/interlisted-companies.txt"
BOARDS = (("tsx", "XTSE", "Toronto Stock Exchange"), ("tsxv", "XTSX", "TSX Venture Exchange"))
SUFFIX_TYPES = [   # סימבולוגיית TMX
    (r"\.PR\.[A-Z0-9]+$", ("Preferred Stock", "מניית בכורה")),
    (r"\.WT(\.[A-Z])?$", ("Warrant", "כתב אופציה")),
    (r"\.DB(\.[A-Z])?$", ("Debenture", "אג\"ח להמרה")),
    (r"\.RT(\.[A-Z])?$", ("Right", "זכויות")),
    (r"\.NT(\.[A-Z])?$", ("Note / Bond", "שטר (Note)")),
]


def figi_tickers(sym):
    """סימול TMX -> מועמדים לטיקר Bloomberg (BBD.B -> BBD/B, BBU.UN -> BBU-U).
    התוצאה מתקבלת רק אם OpenFIGI מחזיר בדיוק את הטיקר המבוקש (בדיקה ב-build.py)."""
    if "." not in sym:
        return [sym]
    parts = sym.split(".")
    base, rest = parts[0], parts[1:]
    if rest == ["UN"]:
        return [f"{base}-U", f"{base}/U"]
    if rest[0] == "PR":
        return [f"{base}/PR/{'/'.join(rest[1:])}", f"{base}-P{''.join(rest[1:])}"]
    return ["/".join(parts), "-".join(parts)]


def build():
    inter = {}
    try:
        for line in get(INTERLISTED).text.splitlines():
            cols = line.split("\t")
            if len(cols) >= 5 and ":" in cols[0]:
                sym, board = cols[0].split(":", 1)
                inter[(board.strip().lower(), sym.strip())] = {"us_symbol": cols[2].strip() or None,
                                                              "sector": cols[3].strip() or None,
                                                              "intl_market": cols[4].strip() or None}
    except Exception as e:  # noqa: BLE001
        log(f"tmx: interlisted failed {e!r}")
    out = []
    for board, mic, exch in BOARDS:
        res = get(DIRECTORY.format(board=board)).json().get("results", [])
        log(f"tmx: {board} {len(res)} companies")
        if len(res) < 500:
            raise RuntimeError(f"tmx: {board} only {len(res)}")
        for c in res:
            for ins in c.get("instruments") or [{"symbol": c["symbol"], "name": c["name"]}]:
                sym = (ins.get("symbol") or "").strip().upper()
                if not sym:
                    continue
                typ = next((t for rx, t in SUFFIX_TYPES if re.search(rx, sym)), None)
                il = inter.get((board, sym)) or {}
                out.append({
                    "id": f"{mic}:{sym}", "isin": None, "market": "CA", "region": "CA", "country": "CA",
                    "name": ins.get("name") or c.get("name"), "issuer_name_exchange": c.get("name"),
                    "company_symbol": c.get("symbol"),
                    "security_type": typ[0] if typ else None, "security_type_he": typ[1] if typ else None,
                    "type_source": "tmx_symbology" if typ else None,
                    "currency": "USD" if re.search(r"\.U$", sym) else "CAD",
                    "primary_mic": mic, "primary_oprt": mic, "primary_source": "exchange", "exchange_name": exch,
                    "listings": [{"m": mic, "o": mic, "cc": "CA", "cat": "RMKT", "r": "TMX"}],
                    "listing_countries": ["CA"],
                    "ticker": sym, "tickers": [sym], "ticker_source": "exchange",
                    "us_symbol": il.get("us_symbol"), "intl_market": il.get("intl_market"),
                    "sector": il.get("sector"),
                    "_figi_tickers": figi_tickers(sym),
                })
    log(f"tmx: {len(out)} instruments, {sum(1 for r in out if r.get('us_symbol'))} interlisted in US")
    return out
