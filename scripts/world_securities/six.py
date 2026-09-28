"""שווייץ - SIX Swiss Exchange (לא חלק מ-FIRDS של האיחוד).

מקורות רשמיים של SIX:
  fqs/ref.csv          - רשימת הניירות לפי סגמנט: EQ מניות, FU קרנות (ETF וקרנות רשומות), EP מוצרי ETP
  equity_issuers.json  - רשימת המנפיקים ברישום: רישום ראשי/משני, תאריך רישום, סוג המניה

"רשום" = כמו באירופה: ברישום של המנפיק. ה-Sponsored Segment (מניות זרות שספונסר מכניס למסחר
בלי המנפיק, ProductLine=PS) לא נכלל - המקבילה של Freiverkehr.
סוג רשמי: CFI מ-FIRDS לאותו ISIN כשקיים (נייר שנסחר גם באיחוד); אחרת לפי הסגמנט של SIX.
"""
import csv
import io

from common import CFI_TYPES, get, log

FQS = "https://www.six-group.com/fqs/ref.csv"
FIELDS = "ShortName,ValorSymbol,ValorNumber,ISIN,TradingBaseCurrency,IssuerNameFull,SecTypeCode,PortalSegment,ProductLine"
ISSUERS = "https://www.six-group.com/sheldon/equity_issuers/v1/equity_issuers.json"
SEGMENT_TYPES = {   # כשאין CFI רשמי ב-FIRDS
    "EQ": ("Common Stock", "מניה רגילה"),
    "FU": ("Investment Fund", "קרן השקעה"),
    "EP": ("ETP", "מוצר נסחר (ETP)"),
}


def fqs(segment):
    r = get(FQS, params={"select": FIELDS, "where": f"PortalSegment={segment}", "page": 1, "pagesize": 99999})
    rows = list(csv.DictReader(io.StringIO(r.content.decode("iso-8859-1")), delimiter=";"))
    log(f"six: {segment} {len(rows)} lines")
    return rows


def build(firds_lookup):
    issuers = {x["isin"]: x for x in get(ISSUERS).json().get("itemList", [])}
    log(f"six: {len(issuers)} equity issuer listings")
    by_isin, stats = {}, {}
    for seg in ("EQ", "FU", "EP"):
        for r in fqs(seg):
            isin = (r.get("ISIN") or "").strip()
            if not isin:
                continue
            key = (seg, r.get("ProductLine"), r.get("SecTypeCode"))
            stats[" / ".join(x or "-" for x in key)] = stats.get(" / ".join(x or "-" for x in key), 0) + 1
            if r.get("ProductLine") == "PS":      # Sponsored Segment - בלי המנפיק
                continue
            row = by_isin.get(isin)
            if row is None:
                row = by_isin[isin] = {"isin": isin, "seg": seg, "tickers": set(), "ccys": set(), "r": r}
            if r.get("ValorSymbol"):
                row["tickers"].add(r["ValorSymbol"].strip())
            if r.get("TradingBaseCurrency"):
                row["ccys"].add(r["TradingBaseCurrency"].strip())
    if len(by_isin) < 1000:
        raise RuntimeError(f"six: only {len(by_isin)} securities")
    out = []
    for isin, x in by_isin.items():
        r, iss, fl = x["r"], issuers.get(isin) or {}, firds_lookup.get(isin) or {}
        cfi = fl.get("cfi")
        if cfi and cfi[:2] in CFI_TYPES:
            typ, tsrc = CFI_TYPES[cfi[:2]], "cfi_" + fl["reg"].lower()
        else:
            typ, tsrc = SEGMENT_TYPES[x["seg"]], "six_segment"
        tickers = sorted(x["tickers"])
        first = str(iss.get("firstListingDate") or "") or None
        out.append({
            "id": isin, "isin": isin, "isin_source": "exchange", "market": "CH", "region": "CH", "country": "CH",
            "name": iss.get("company") or r.get("IssuerNameFull") or r.get("ShortName"),
            "short_name": r.get("ShortName"), "cfi": cfi,
            "security_type": typ[0], "security_type_he": typ[1], "type_source": tsrc,
            "exchange_segment": x["seg"], "exchange_product_line": r.get("ProductLine"),
            "exchange_sec_type": r.get("SecTypeCode"), "share_class_desc": iss.get("classOfShare"),
            "currency": ",".join(sorted(x["ccys"])) or None, "lei": fl.get("lei"),
            "issuer_name_exchange": r.get("IssuerNameFull"),
            "issuer_country_exchange": iss.get("country"),
            "primary_listing": {True: 1, False: 0}.get(iss.get("primaryListing")),
            "second_line": 1 if iss.get("secondLineReasonCode") else None,
            "primary_mic": "XSWX", "primary_oprt": "XSWX", "primary_source": "exchange",
            "listings": [{"m": "XSWX", "o": "XSWX", "cc": "CH", "cat": "RMKT", "r": "SIX"}],
            "listing_countries": ["CH"],
            "ticker": tickers[0] if len(tickers) == 1 else None, "tickers": tickers, "ticker_source": "exchange",
            "valor": r.get("ValorNumber") or (str(iss["valorNumber"]) if iss.get("valorNumber") else None),
            "first_trade_date": f"{first[:4]}-{first[4:6]}-{first[6:8]}" if first and len(first) == 8 else None,
        })
    log(f"six: {len(out)} listed securities; lines by segment/productline/sectype: {stats}")
    return out
