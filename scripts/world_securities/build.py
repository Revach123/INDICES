"""מאגר ניירות ערך עולמי - אירופה+בריטניה (ESMA/FCA FIRDS), שווייץ (SIX), יפן (JPX), קנדה (TMX).

שלבים:
  1. ISO 10383 - טבלת ה-MIC (שמות בורסות, מדינה, סוג שוק)
  2. כל שוק בנפרד, "הכל או כלום" (שוק שנכשל - השורות שלו נשארות מהריצה הקודמת)
  3. GLEIF - פרטי המנפיק לכל LEI
  4. OpenFIGI לפי MIC - טיקר ו-FIGI בבורסה הרלוונטית (בלי מפתח: 250 בדיקות לדקה, במטמון)
  5. מיזוג עם הריצה הקודמת (לא מוחקים; removed_at), סטטיסטיקה ופלט

פלט (data/world_securities/): securities.jsonl, issuers.jsonl, exchanges.json, stats.json,
figi_cache.jsonl, gleif_cache.jsonl. נצרך ע"י Revach (טעינה ל-D1 וזיהוי אחזקות קרנות).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import src_firds as firds  # noqa: E402
import src_jpx as jpx  # noqa: E402
import src_six as six  # noqa: E402
import src_tmx as tmx  # noqa: E402
from common import (CATEGORY_BY_TYPE, NOW_ISO, OUT_DIR, TODAY, count, dominant_exch_codes, figi_lookup,  # noqa: E402
                    figi_pick, gleif_enrich, load_mics, log)

SECURITIES = os.path.join(OUT_DIR, "securities.jsonl")
ISSUERS = os.path.join(OUT_DIR, "issuers.jsonl")
EXCHANGES = os.path.join(OUT_DIR, "exchanges.json")
STATS = os.path.join(OUT_DIR, "stats.json")
FIGI_CACHE = os.path.join(OUT_DIR, "figi_cache.jsonl")
GLEIF_CACHE = os.path.join(OUT_DIR, "gleif_cache.jsonl")
MIN_RATIO = 0.8
FIGI_BUDGET = int(os.environ.get("OPENFIGI_BUDGET", "2400"))
GLEIF_BUDGET = int(os.environ.get("GLEIF_BUDGET", "1500"))
ONLY = set(filter(None, os.environ.get("WORLD_MARKETS", "").split(",")))   # לבדיקות: EU_UK,CH,JP,CA

FIGI_FIELDS = ("figi", "share_class_figi", "figi_security_type", "figi_exch_code")
ISSUER_FIELDS = ("issuer_name", "issuer_country", "issuer_city", "issuer_hq_country", "issuer_status",
                 "issuer_category")
# סוג לפי OpenFIGI (securityType של Bloomberg) - רק לקנדה, שם אין סיווג בורסה מלא
FIGI_TYPES = {
    "Common Stock": ("Common Stock", "מניה רגילה"), "ETP": ("ETF", "קרן סל (ETF)"),
    "REIT": ("REIT Stock", "מניית ריט (REIT)"), "Preference": ("Preferred Stock", "מניית בכורה"),
    "Preferred": ("Preferred Stock", "מניית בכורה"), "Unit": ("Unit", "יחידה"),
    "Right": ("Right", "זכויות"), "Warrant": ("Warrant", "כתב אופציה"),
    "Closed-End Fund": ("Closed-End Fund", "קרן סגורה"), "Mutual Fund": ("Investment Fund", "קרן השקעה"),
    "Depositary Receipt": ("Depositary Receipt", "תעודת פיקדון (DR)"),
    "Canadian DR": ("Depositary Receipt", "תעודת פיקדון (DR)"),
    "Ltd Part": ("Limited Partnership", "יחידת שותפות"), "MLP": ("Limited Partnership", "יחידת שותפות"),
    "Royalty Trst": ("Trust Units", "יחידת נאמנות"), "Income Trust": ("Trust Units", "יחידת נאמנות"),
    "Stapled Security": ("Stapled Security", "נייר צמוד (Stapled)"),
}
CATEGORY_BY_TYPE.update({"Closed-End Fund": "funds", "Trust Units": "stocks", "Stapled Security": "stocks",
                         "ETP": "etf", "Note / Bond": "other"})


def read_jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    out.append(json.loads(line))
    except FileNotFoundError:
        pass
    return out


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
    os.replace(path + ".tmp", path)


def read_cache(path):
    return {r["k"]: r["v"] for r in read_jsonl(path)}


def write_cache(path, cache):
    write_jsonl(path, [{"k": k, "v": cache[k]} for k in sorted(cache)])


def fetch_markets(mics, prev_active):
    results, failed, meta = {}, {}, {}
    firds_lookup = {}
    if not ONLY or "EU_UK" in ONLY or "CH" in ONLY:
        try:
            rows, firds_lookup, meta = firds.build(mics)
            if not ONLY or "EU_UK" in ONLY:
                results["EU_UK"] = rows
        except Exception as e:  # noqa: BLE001
            failed["EU_UK"] = repr(e)
    builders = {"CH": lambda: six.build(firds_lookup) if firds_lookup else (_ for _ in ()).throw(
                    RuntimeError("CH needs FIRDS lookup (official CFI/LEI)")),
                "JP": jpx.build, "CA": tmx.build}
    for m, fn in builders.items():
        if ONLY and m not in ONLY:
            continue
        try:
            results[m] = fn()
        except Exception as e:  # noqa: BLE001
            failed[m] = repr(e)
    for m, rows in list(results.items()):
        p = prev_active.get(m, 0)
        if p and len(rows) < p * MIN_RATIO:
            failed[m] = f"only {len(rows)} rows vs {p} active last run"
            del results[m]
    for m, err in failed.items():
        log(f"MARKET FAILED {m}: {err} - keeping previous rows")
    return results, failed, meta, firds_lookup


def merge_swiss_into_eu(results):
    """ISIN שרשום גם באיחוד/בריטניה וגם ב-SIX (בעיקר קרנות סל) = שורה אחת עם כל הבורסות.
    ב-SIX רישום ראשי רשמי (primaryListing) גובר על קביעת השוק העיקרי מ-FIRDS."""
    eu = {r["isin"]: r for r in results.get("EU_UK", [])}
    ch_rows, merged = [], 0
    for r in results.get("CH", []):
        e = eu.get(r["isin"])
        if e is None:
            ch_rows.append(r)
            continue
        merged += 1
        e["listings"] = [l for l in e["listings"] if l["m"] != "XSWX"] + [
            dict(r["listings"][0], t=",".join(r["tickers"]) or None)]
        e["listing_countries"] = sorted(set(e["listing_countries"]) | {"CH"})
        e["six_ticker"] = ",".join(r["tickers"]) or None
        e["valor"] = r.get("valor")
        if r.get("primary_listing") == 1:
            e.update({"primary_mic": "XSWX", "primary_oprt": "XSWX", "primary_source": "exchange",
                      "country": "CH", "region": "CH"})
    if "CH" in results:
        results["CH"] = ch_rows
    log(f"six: {merged} ISINs also listed in EU/UK - merged into one row")
    return [r for rows in results.values() for r in rows]


EUROPE = firds.EEA | {"GB", "CH"}


def fill_isin_from_share_class(rows, cache, dominant):
    """יפן/קנדה (המקורות בלי ISIN): ISIN רשמי מ-FIRDS/SIX של אותו נייר בדיוק - שורה אירופית עם
    אותו Share Class FIGI וקידומת ISIN של מדינת הבורסה (CA/JP). רק התאמה יחידה."""
    by_sc = {}
    for r in rows:
        if r["market"] in ("EU_UK", "CH") and r.get("isin"):
            apply_figi(r, cache, dominant)
            if r.get("share_class_figi"):
                by_sc.setdefault(r["share_class_figi"], set()).add(r["isin"])
    filled = 0
    for r in rows:
        if r["market"] in ("JP", "CA") and not r.get("isin"):
            apply_figi(r, cache, dominant)
            isins = {i for i in by_sc.get(r.get("share_class_figi") or "", set()) if i[:2] == r["country"]}
            if len(isins) == 1:
                r["isin"], r["isin_source"] = next(iter(isins)), "firds_share_class"
                filled += 1
    log(f"isin: {filled} JP/CA securities got the regulator's ISIN via the same share-class FIGI")


HOME_MICS = {"JP": ("XTKS",), "CA": ("XTSE", "XTSX")}


def home_isin_jobs(firds_lookup):
    """ISIN-ים רשמיים של מניות/קרנות יפניות וקנדיות מ-FIRDS (נסחרות גם באירופה) -> OpenFIGI בבורסת
    הבית, כדי לקבל את הקוד/סימול שם ולהשלים ISIN לשורה של JPX/TMX."""
    jobs = {}
    for isin, a in sorted(firds_lookup.items()):
        cc = isin[:2]
        if cc in HOME_MICS and (a.get("cfi") or "")[:1] in ("E", "C"):
            for mic in HOME_MICS[cc]:
                jobs[f"{isin}@{mic}"] = {"idType": "ID_ISIN", "idValue": isin, "micCode": mic}
    return jobs


def fill_isin_from_home_lookup(rows, cache, dominant):
    """ISIN -> (MIC, טיקר) מ-OpenFIGI; שיוך רק כשהמיפוי חד-חד-ערכי (ISIN אחד לקוד, קוד אחד ל-ISIN)."""
    by_ticker = {}
    for k, e in cache.items():
        mic = (e.get("job") or {}).get("micCode")
        if "@" not in k or mic not in ("XTKS", "XTSE", "XTSX") or not e.get("data"):
            continue
        p = figi_pick(e, dominant)
        if p and p["ticker"]:
            by_ticker.setdefault((mic, p["ticker"]), set()).add(e["job"]["idValue"])
    isin_count = {}
    for isins in by_ticker.values():
        for i in isins:
            isin_count[i] = isin_count.get(i, 0) + 1
    filled = 0
    for r in rows:
        if r["market"] not in ("JP", "CA") or r.get("isin"):
            continue
        tickers = [r["ticker"]] if r["market"] == "JP" else (r.get("_figi_tickers") or [])
        cands = set()
        for t in tickers:
            cands |= by_ticker.get((r["primary_mic"], t), set())
        cands = {i for i in cands if isin_count.get(i) == 1}
        if len(cands) == 1:
            r["isin"], r["isin_source"] = next(iter(cands)), "firds_openfigi"
            filled += 1
    log(f"isin: {filled} JP/CA securities got an official FIRDS ISIN via OpenFIGI at the home exchange")


def figi_jobs(rows, extra=None):
    """key -> job. סדר: שווקים קטנים קודם (נגמרים מהר), אחר כך ראשי באירופה, ISIN-ים של יפן/קנדה,
    אחר כך שאר הבורסות."""
    first, eu_primary, eu_other = {}, {}, {}
    for r in rows:
        if r["market"] == "JP":
            first[r["id"]] = {"idType": "TICKER", "idValue": r["ticker"], "micCode": "XTKS"}
        elif r["market"] == "CA":
            for t in r.get("_figi_tickers") or []:
                first[f"{r['primary_mic']}:{t}"] = {"idType": "TICKER", "idValue": t, "micCode": r["primary_mic"]}
        elif r["market"] == "CH":
            first[f"{r['isin']}@XSWX"] = {"idType": "ID_ISIN", "idValue": r["isin"], "micCode": "XSWX"}
        else:
            if r.get("primary_oprt"):
                eu_primary[f"{r['isin']}@{r['primary_oprt']}"] = {"idType": "ID_ISIN", "idValue": r["isin"],
                                                                  "micCode": r["primary_oprt"]}
            else:
                for o in sorted({l["o"] for l in r["listings"]}):
                    eu_other[f"{r['isin']}@{o}"] = {"idType": "ID_ISIN", "idValue": r["isin"], "micCode": o}
    return {**first, **eu_primary, **(extra or {}), **eu_other}


def apply_figi(r, cache, dominant):
    """קובע טיקר/FIGI מהמטמון. מחזיר False אם הבדיקה עוד לא בוצעה (אז שומרים ערכים קודמים)."""
    m = r["market"]
    if m == "JP":
        e = cache.get(r["id"])
        if e is None:
            return False
        p = figi_pick(e, dominant)
        if p and p["tickers"] != [r["ticker"]]:
            p = None   # רק התאמה מדויקת לקוד
        r.update({k: (p or {}).get(k) for k in FIGI_FIELDS})
        return True
    if m == "CA":
        keys = [f"{r['primary_mic']}:{t}" for t in r.get("_figi_tickers") or []]
        if any(k not in cache for k in keys):
            return False
        for k, t in zip(keys, r["_figi_tickers"]):
            e = cache[k]
            rows = [d for d in (e.get("data") or []) if d.get("ticker") == t]
            p = figi_pick(dict(e, data=rows), dominant) if rows else None
            if p and p["figi"]:
                r.update({f: p.get(f) for f in FIGI_FIELDS})
                r["figi_ticker"] = t
                return True
        r.update({k: None for k in FIGI_FIELDS})
        return True
    if m == "CH":
        e = cache.get(f"{r['isin']}@XSWX")
        if e is None:
            return False
        p = figi_pick(e, dominant) or {}
        r.update({k: p.get(k) for k in FIGI_FIELDS})
        return True
    # אירופה/בריטניה - טיקר ו-FIGI מהבורסה הראשית, או לכל בורסה ברישום
    oprts = [r["primary_oprt"]] if r.get("primary_oprt") else sorted({l["o"] for l in r["listings"]})
    if any(f"{r['isin']}@{o}" not in cache for o in oprts):
        return False
    per = {}
    for o in oprts:
        p = figi_pick(cache[f"{r['isin']}@{o}"], dominant)
        if p:
            per[o] = p
    for l in r["listings"]:
        if l.get("r") == "SIX" and l.get("t"):
            continue      # טיקר רשמי מ-SIX
        p = per.get(l["o"])
        l["t"] = ",".join(p["tickers"]) if p and p["tickers"] else None
    if r.get("primary_oprt"):
        p = per.get(r["primary_oprt"]) or {}
        r["ticker"], r["tickers"] = p.get("ticker"), p.get("tickers") or []
        r.update({k: p.get(k) for k in FIGI_FIELDS})
    else:
        r["ticker"] = None
        r["tickers"] = sorted({t for p in per.values() for t in p["tickers"]})
        shares = {p.get("share_class_figi") for p in per.values() if p.get("share_class_figi")}
        r.update({k: None for k in FIGI_FIELDS})
        r["share_class_figi"] = next(iter(shares)) if len(shares) == 1 else None
    r["ticker_source"] = "openfigi" if r["tickers"] else None
    return True


def main():
    prev_rows = {r["id"]: r for r in read_jsonl(SECURITIES)}
    prev_active = {}
    for r in prev_rows.values():
        if r.get("last_seen_active"):
            prev_active[r["market"]] = prev_active.get(r["market"], 0) + 1
    figi_cache = read_cache(FIGI_CACHE)
    gleif_cache = read_cache(GLEIF_CACHE)

    mics = load_mics()
    results, failed, meta, firds_lookup = fetch_markets(mics, prev_active)
    if not results:
        sys.exit("ABORT: all markets failed")

    today = merge_swiss_into_eu(results)
    # נרמול בורסות לפי טבלת ה-MIC
    for r in today:
        if r.get("primary_mic"):
            m = mics.get(r["primary_mic"]) or {}
            r["primary_oprt"] = m.get("oprt") or r.get("primary_oprt") or r["primary_mic"]
            r["country"] = r.get("country") or m.get("cc")
        for l in r["listings"]:
            l["o"] = (mics.get(l["m"]) or {}).get("oprt") or l["o"]
        names = []
        for o in ([r["primary_oprt"]] if r.get("primary_oprt") else []) + sorted({l["o"] for l in r["listings"]}):
            n = (mics.get(o) or {}).get("short") or o
            if n not in names:
                names.append(n)
        r["primary_exchange"] = ((mics.get(r["primary_oprt"]) or {}).get("short") or r["primary_oprt"]
                                 if r.get("primary_oprt") else None)
        r["exchange_names"] = "; ".join(names)
        r["listing_mics"] = sorted({l["o"] for l in r["listings"]} | {l["m"] for l in r["listings"]})
        # רישום משני של חברה זרה: ISIN של מדינה מחוץ לאירופה, שונה ממדינת הבורסה (Apple ב-Warsaw
        # Global Connect, Bank of Montreal בבורסת סופיה). נתון רשמי - מסומן, לא מוסתר.
        home = (r.get("isin") or "")[:2]
        r["foreign_listing"] = 1 if (r["market"] in ("EU_UK", "CH") and home and home not in EUROPE
                                     and home != r.get("country")) else None

    # GLEIF
    leis = {r["lei"] for r in today if r.get("lei")}
    try:
        gleif_enrich(leis, gleif_cache, GLEIF_BUDGET)
    except Exception as e:  # noqa: BLE001
        log(f"gleif FAILED {e!r}")

    # OpenFIGI
    try:
        figi_lookup(figi_jobs(today, home_isin_jobs(firds_lookup)), figi_cache, FIGI_BUDGET)
    except Exception as e:  # noqa: BLE001
        log(f"openfigi FAILED {e!r}")
    dominant = dominant_exch_codes(figi_cache)
    log(f"openfigi: dominant exchCode per MIC: {dict(sorted(dominant.items()))}")

    fill_isin_from_share_class(today, figi_cache, dominant)
    fill_isin_from_home_lookup(today, figi_cache, dominant)

    # מיזוג
    out = {}
    pending = 0
    for r in today:
        old = prev_rows.get(r["id"]) or {}
        done = apply_figi(r, figi_cache, dominant)
        if not done:
            pending += 1
            for k in FIGI_FIELDS + ("ticker", "tickers", "figi_ticker", "ticker_source"):
                if r.get(k) in (None, [], "") and old.get(k) not in (None, [], ""):
                    r[k] = old[k]
        if r["market"] in ("JP", "CA") and not r.get("isin") and old.get("isin"):
            r["isin"], r["isin_source"] = old["isin"], old.get("isin_source")   # התאמה מדויקת מריצה קודמת
        if r["market"] == "CA" and r.get("type_source") is None:
            t = FIGI_TYPES.get(r.get("figi_security_type") or "")
            if t:
                r["security_type"], r["security_type_he"], r["type_source"] = t[0], t[1], "openfigi"
            elif r.get("figi_security_type"):
                r["security_type"], r["security_type_he"], r["type_source"] = "Other", "אחר", "openfigi"
                r["figi_type_unmapped"] = r["figi_security_type"]
            elif old.get("type_source") in ("openfigi",) and not done:
                r["security_type"], r["security_type_he"], r["type_source"] = (
                    old["security_type"], old["security_type_he"], old["type_source"])
        if not r.get("security_type"):
            r["security_type"], r["security_type_he"], r["type_source"] = None, "לא מסווג", None
        r["category"] = CATEGORY_BY_TYPE.get(r["security_type"] or "", "other" if r["security_type"] else "unclassified")
        g = gleif_cache.get(r.get("lei")) or {}
        if g and not g.get("missing"):
            r.update({"issuer_name": g.get("name"), "issuer_country": g.get("country"), "issuer_city": g.get("city"),
                      "issuer_hq_country": g.get("hq_country"), "issuer_status": g.get("status"),
                      "issuer_category": g.get("category")})
        elif r.get("lei") and r["lei"] not in gleif_cache:
            for k in ISSUER_FIELDS:
                r[k] = old.get(k)
        r.pop("_figi_tickers", None)
        row = dict(r)
        row["first_seen_at"] = old.get("first_seen_at") or TODAY
        row["last_seen_at"] = TODAY
        row["last_seen_active"] = 1
        row["removed_at"] = None
        out[r["id"]] = {k: v for k, v in row.items() if v not in (None, "", [])} | {"last_seen_active": 1}
    log(f"merge: {len(out)} active today, {pending} with OpenFIGI lookup pending")
    for k, old in prev_rows.items():
        if k in out:
            continue
        if old["market"] in results:          # השוק נקרא בהצלחה והנייר לא שם - ירד
            old = dict(old, last_seen_active=0)
            old["removed_at"] = old.get("removed_at") or TODAY
        out[k] = old

    rows = [out[k] for k in sorted(out)]
    active = [r for r in rows if r.get("last_seen_active")]
    used_leis = {}
    for r in active:
        if r.get("lei"):
            used_leis[r["lei"]] = used_leis.get(r["lei"], 0) + 1
    issuers = []
    for lei in sorted(used_leis):
        g = gleif_cache.get(lei) or {}
        if g and not g.get("missing"):
            issuers.append({"lei": lei, **{k: v for k, v in g.items() if k != "d" and v is not None},
                            "securities_count": used_leis[lei], "fetched_at": g.get("d")})
    used_mics = sorted({m for r in active for m in r.get("listing_mics", [])} |
                       {r["primary_oprt"] for r in active if r.get("primary_oprt")})
    exchanges = {m: mics[m] for m in used_mics if m in mics}

    stats = {"generated_at": NOW_ISO, "failed_markets": failed, "firds_files": meta,
             "mic_samples": {m: mics.get(m) for m in ("XLON", "XLOM", "AIMX", "XPAR", "XETR", "XMIL", "XTKS", "XTSE")},
             "total": len(rows), "active": len(active),
             "by_market": count(active, "market"), "by_region": count(active, "region"),
             "by_country": count(active, "country"),
             "by_type": count(active, "security_type"), "by_type_source": count(active, "type_source"),
             "by_category": count(active, "category"), "by_primary_source": count(active, "primary_source"),
             "with_ticker": sum(1 for r in active if r.get("tickers")),
             "with_figi": sum(1 for r in active if r.get("figi")),
             "with_share_class_figi": sum(1 for r in active if r.get("share_class_figi")),
             "with_lei": sum(1 for r in active if r.get("lei")),
             "with_issuer": sum(1 for r in active if r.get("issuer_name")),
             "with_isin": sum(1 for r in active if r.get("isin")),
             "issuers": len(issuers), "exchanges": len(exchanges),
             "by_market_detail": {m: {"n": sum(1 for r in active if r["market"] == m),
                                      "ticker": sum(1 for r in active if r["market"] == m and r.get("tickers")),
                                      "figi": sum(1 for r in active if r["market"] == m and r.get("figi")),
                                      "types": count([r for r in active if r["market"] == m], "security_type")}
                                  for m in ("EU_UK", "CH", "JP", "CA")},
             "unmapped_figi_types": count([r for r in active if r.get("figi_type_unmapped")], "figi_type_unmapped"),
             "figi_pending": pending}
    log("stats: " + json.dumps(stats, ensure_ascii=False))
    write_jsonl(SECURITIES, rows)
    write_jsonl(ISSUERS, issuers)
    with open(EXCHANGES, "w", encoding="utf-8") as f:
        json.dump(exchanges, f, ensure_ascii=False, indent=0, sort_keys=True)
    with open(STATS, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1, sort_keys=True)
    write_cache(FIGI_CACHE, figi_cache)
    write_cache(GLEIF_CACHE, gleif_cache)


if __name__ == "__main__":
    main()
