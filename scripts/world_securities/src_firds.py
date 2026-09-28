"""אירופה (ESMA FIRDS) ובריטניה (FCA FIRDS) - קבצי FULINS השבועיים המלאים.

לכל ISIN הרגולטור מפרסם: שם, קוד CFI (סוג רשמי), מטבע, LEI של המנפיק, ולכל זירת מסחר (MIC)
האם המנפיק ביקש/אישר את הרישום (IssrReq) ותאריך מסחר ראשון/סיום. בנוסף TechAttrbts/RlvntTradgVn -
"הזירה הרלוונטית ביותר" שקבע הרגולטור.

"רשום בבורסה" אצלנו = יש לפחות זירה אחת עם IssrReq=true (רישום ביוזמת/באישור המנפיק) שלא הסתיים
בה המסחר, ושאינה במפורש זירה שאינה בורסה (SI/OTF/ספקי דיווח - ר' NON_EXCHANGE_CATS). כך נכנסים שוק
ראשי + שווקי צמיחה (AIM, Euronext Growth, First North), ולא נכנס מסחר משני בלי המנפיק
(Freiverkehr/Tradegate) או מוצרים מובנים של בנקים (CFI EY).

שוק עיקרי (primary_mic), לפי הסדר, רק אם חד-משמעי:
  rlvnt        - הזירה הרלוונטית של הרגולטור, אם היא אחת מזירות הרישום
  single       - יש רק בורסה (operating MIC) אחת ברישום
  home_country - בורסה יחידה ברישום במדינת ה-ISIN
אחרת ריק - ומוצגת רשימת כל הבורסות.
"""
import datetime
import io
import re
import time
import zipfile
from xml.etree.ElementTree import iterparse

from common import CFI_TYPES, NOW, TODAY, get, log

ESMA_FILES = "https://registers.esma.europa.eu/solr/esma_registers_firds_files/select"
FCA_FILES = "https://api.data.fca.org.uk/fca_data_firds_files"
CATEGORIES = ("E", "C")
# הקטגוריה ב-ISO 10383 לא אמינה לשווקים (כל ה-LSE כולל AIM, Euronext Growth, First North ו-Euro MTF
# מסומנים NSPD - "לא מוגדר"), לכן הסימן לרישום הוא IssrReq של הרגולטור, והקטגוריה משמשת רק להוצאת
# זירות שבמפורש אינן בורסה: מבצע מסחר עצמי (SINT), OTF, וספקי דיווח/נתונים (APA/ARM/CTP/CASP).
NON_EXCHANGE_CATS = {"SINT", "OTFS", "APPA", "ARMS", "CTPS", "CASP"}
SKIP_CFI2 = {"EY"}     # מוצרים מובנים (תעודות/אופציות בנקאיות) - לא ניירות של מנפיק ברישום
FILE_RX = re.compile(r"^FULINS_([A-Z])_(\d{8})_(\d+)of(\d+)\.zip$")
EEA = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU",
       "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "IS", "LI", "NO"}


def _latest_complete(files):
    """files: [(name, link)] -> {cat: [links]} לתאריך האחרון שבו כל הקטגוריות שלמות."""
    by = {}
    for name, link in files:
        m = FILE_RX.match(name or "")
        if m and m.group(1) in CATEGORIES:
            cat, date, i, n = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
            by.setdefault(date, {}).setdefault(cat, {"n": n, "parts": {}})["parts"][i] = link
    for date in sorted(by, reverse=True):
        d = by[date]
        if all(c in d and len(d[c]["parts"]) == d[c]["n"] for c in CATEGORIES):
            return date, {c: [d[c]["parts"][i] for i in sorted(d[c]["parts"])] for c in CATEGORIES}
    raise RuntimeError(f"no complete FULINS set among {sorted(by)}")


def _since():
    return (NOW.date() - datetime.timedelta(days=21)).isoformat()


def list_esma():
    f = _since()
    r = get(ESMA_FILES, params={"q": "*", "fq": f"publication_date:[{f}T00:00:00Z TO {TODAY}T23:59:59Z]",
                                "wt": "json", "start": 0, "rows": 1000})
    docs = r.json()["response"]["docs"]
    return _latest_complete([(d.get("file_name"), d.get("download_link")) for d in docs])


def list_fca():
    f = _since()
    r = get(FCA_FILES, params={"q": f"((file_type:FULINS) AND (publication_date:[{f} TO {TODAY}]))",
                               "from": 0, "size": 1000})
    src = [h.get("_source", {}) for h in r.json().get("hits", {}).get("hits", [])]
    return _latest_complete([(d.get("file_name"), d.get("download_link")) for d in src])


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def parse_zip(content, agg):
    """מצטבר לפי ISIN: {name, short, cfi, ccy, lei, req: {mic: first_trade}, n_venues, rlvnt, nca}."""
    rows = 0
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for member in z.namelist():
            with z.open(member) as f:
                for _, el in iterparse(f, events=("end",)):
                    if _local(el.tag) != "RefData":
                        continue
                    rows += 1
                    g, lei, venues, tech = {}, None, [], {}
                    for part in el:
                        p = _local(part.tag)
                        if p == "FinInstrmGnlAttrbts":
                            g = {_local(c.tag): (c.text or "").strip() for c in part}
                        elif p == "Issr":
                            lei = (part.text or "").strip()
                        elif p == "TradgVnRltdAttrbts":
                            venues.append({_local(c.tag): (c.text or "").strip() for c in part})
                        elif p == "TechAttrbts":
                            tech = {_local(c.tag): (c.text or "").strip() for c in part}
                    el.clear()
                    isin, cfi = g.get("Id"), g.get("ClssfctnTp") or ""
                    if not isin or cfi[:2] in SKIP_CFI2:
                        continue
                    a = agg.get(isin)
                    if a is None:
                        a = agg[isin] = {"name": g.get("FullNm"), "short": g.get("ShrtNm"), "cfi": cfi,
                                         "ccy": g.get("NtnlCcy"), "lei": lei, "req": {}, "n_venues": 0,
                                         "rlvnt": None, "nca": None}
                    for venue in venues:
                        term = venue.get("TermntnDt")
                        if term and term[:10] < TODAY:
                            continue
                        a["n_venues"] += 1
                        mic = venue.get("Id")
                        if venue.get("IssrReq") == "true" and mic:
                            a["req"][mic] = (venue.get("FrstTradDt") or "")[:10] or None
                    if tech.get("RlvntTradgVn"):
                        a["rlvnt"] = tech["RlvntTradgVn"]
                    if tech.get("RlvntCmptntAuthrty"):
                        a["nca"] = tech["RlvntCmptntAuthrty"]
    return rows


def load_regulator(name, lister):
    date, cats = lister()
    agg, total = {}, 0
    for cat, links in cats.items():
        for link in links:
            t = time.monotonic()
            content = get(link, timeout=900).content
            n = parse_zip(content, agg)
            total += n
            log(f"firds {name}: {link.rsplit('/', 1)[-1]} {len(content) / 1e6:.1f}MB, {n} rows, "
                f"{time.monotonic() - t:.0f}s")
    log(f"firds {name}: set {date} - {total} rows, {len(agg)} ISINs")
    if len(agg) < 5000:
        raise RuntimeError(f"{name}: only {len(agg)} ISINs")
    return date, agg


def build(mics):
    """מחזיר (rows, lookup, meta). lookup = כל ה-ISIN-ים בשני הקבצים (גם לא רשומים) -> cfi/lei/name,
    להעשרת שווקים אחרים (שווייץ) בסוג רשמי וב-LEI."""
    regs = {}
    meta = {}
    for name, lister in (("ESMA", list_esma), ("FCA", list_fca)):
        date, agg = load_regulator(name, lister)
        regs[name] = agg
        meta[name] = date

    def oprt(mic):
        return (mics.get(mic) or {}).get("oprt") or mic

    rows, dropped = [], {}
    isins = set(regs["ESMA"]) | set(regs["FCA"])
    for isin in isins:
        e, f = regs["ESMA"].get(isin), regs["FCA"].get(isin)
        listings = {}
        for reg, a in (("ESMA", e), ("FCA", f)):
            for mic, first in ((a or {}).get("req") or {}).items():
                m = mics.get(mic) or {}
                if m.get("cat") in NON_EXCHANGE_CATS:
                    dk = f"{mic}|{m.get('cat') or '?'}|{m.get('status') or '?'}"
                    dropped[dk] = dropped.get(dk, 0) + 1
                    continue
                if mic in listings:
                    listings[mic]["r"] = "ESMA+FCA"
                    continue
                listings[mic] = {"m": mic, "o": oprt(mic), "cc": m.get("cc"), "cat": m.get("cat"), "r": reg,
                                 "first": first}
        if not listings:
            continue
        base = e or f
        cfi = base["cfi"]
        # ראשי
        cands = {}
        for reg, a in (("ESMA", e), ("FCA", f)):
            rv = (a or {}).get("rlvnt")
            if rv and (rv in listings or any(l["o"] == oprt(rv) for l in listings.values())):
                cands[reg] = rv
        oprts = sorted({l["o"] for l in listings.values()})
        primary, psrc = None, None
        if len({oprt(v) for v in cands.values()}) == 1:
            primary, psrc = next(iter(cands.values())), "rlvnt"
        elif len(oprts) == 1:
            primary, psrc = next(l["m"] for l in listings.values()), "single"
        else:
            home = sorted({l["o"] for l in listings.values() if l["cc"] == isin[:2]})
            if len(home) == 1:
                primary = next(l["m"] for l in listings.values() if l["o"] == home[0])
                psrc = "home_country"
        # המנפיק/שם לפי הרגולטור של השוק העיקרי (אם ידוע), אחרת ESMA
        pcc = (mics.get(primary) or {}).get("cc") if primary else None
        src = f if (pcc == "GB" and f) else base
        typ = CFI_TYPES.get(cfi[:2], ("Other", "אחר"))
        countries = sorted({l["cc"] for l in listings.values() if l["cc"]})
        region = ("UK" if pcc == "GB" else "EU") if pcc else ("EU" if any(c in EEA for c in countries) else "UK")
        rows.append({
            "id": isin, "isin": isin, "isin_source": "regulator", "market": "EU_UK", "region": region,
            "name": src.get("name"), "short_name": src.get("short"), "cfi": cfi,
            "security_type": typ[0], "security_type_he": typ[1],
            "type_source": "cfi_" + ("fca" if src is f else "esma"),
            "currency": src.get("ccy"), "lei": src.get("lei"),
            "primary_mic": primary, "primary_oprt": oprt(primary) if primary else None, "primary_source": psrc,
            "country": pcc, "listings": sorted(listings.values(), key=lambda l: (l["o"], l["m"])),
            "listing_countries": countries, "n_venues": (e or {}).get("n_venues", 0) + (f or {}).get("n_venues", 0),
            "first_trade_date": min((l["first"] for l in listings.values() if l.get("first")), default=None),
            "regulators": [r for r, a in (("ESMA", e), ("FCA", f)) if a and a.get("req")],
            "source_file_date": max(meta.values()),
        })
    lookup = {}
    for reg in ("FCA", "ESMA"):   # ESMA גובר
        for isin, a in regs[reg].items():
            lookup[isin] = {"cfi": a["cfi"], "lei": a["lei"], "name": a["name"], "ccy": a["ccy"], "reg": reg}
    top = dict(sorted(dropped.items(), key=lambda kv: -kv[1])[:40])
    log(f"firds: {len(rows)} listed securities; non-RM/MTF issuer venues dropped (mic|cat|status): {top}")
    meta = dict(meta, dropped_issuer_venues=top)
    return rows, lookup, meta
