"""אג"ח עולמיות -> המנפיק (LEI) -> חברת האם. נפרד לחלוטין מ-build.py: קבצים, workflow ותיקיית פלט משלו
(data/world_bonds/), כך שמאגר המניות/קרנות (data/world_securities/) והטבלאות שנבנות ממנו לא משתנים.

מקורות (רשמיים בלבד, בלי ניחוש משמות):
  1. ESMA FIRDS + FCA FIRDS, קבצי FULINS_D (מכשירי חוב) - כל אג"ח שנסחרת בזירה באיחוד/בבריטניה, כפי שהבורסות
     (לוקסמבורג, Euronext Dublin, פרנקפורט, לונדון...) מדווחות לרגולטור: ISIN, שם, CFI, מטבע, פדיון, LEI המנפיק.
     מוצרים מובנים בנקאיים (CFI DE/DS - תעודות) נכללים ומסומנים בנפרד.
  1b. GLEIF ISIN-LEI mapping (ANNA - סוכנויות המספור): המקור הראשון למנפיק; FIRDS רק כשאין בו.
  2. GLEIF golden copy - רמה 1 (שם המנפיק, מדינה, מספר רישום ורשם) ורמה 2 (חברת אם ישירה/סופית לפי איחוד דוחות),
     למנפיקים שנמצאו ולחברות האם שלהם.

פלט (data/world_bonds/):
  isin/<CC>.csv.gz   - isin,lei,cfi,ccy,maturity,short_name לפי שתי האותיות הראשונות של ה-ISIN (חיפוש מהיר)
  issuers.jsonl      - lei -> שם, מדינה, רשם + מספר רישום, קטגוריה, חברת אם ישירה/סופית (LEI + שם)
  stats.json
  site/              - קבצים לדף האתר (Revach: securities-world-bonds.html), ר' write_site
"""
import csv
import gzip
import hashlib
import io
import json
import os
import re
import time
import zipfile
from collections import Counter, defaultdict
from xml.etree.ElementTree import iterparse

from common import NOW_ISO, TODAY, get, log
import src_firds

OUT = os.environ.get("BONDS_OUT_DIR", "data/world_bonds")
SKIP_CFI2 = set()
STRUCT_CFI2 = {"DE", "DS"}        # מוצרים מובנים (תעודות בנקאיות) - נכללים, ומסומנים בנפרד בדף (מתג אג"ח/תעודות)
LEI_CAP = 2000                    # מכשירים לכל סוג (אג"ח / מובנים) לכל מנפיק בקבצי הדף
ISIN_SHARD_MAX = 25000            # ISIN-ים לקובץ חיפוש בדף לפני פיצול לקידומת ארוכה יותר
ISIN_MAP_LATEST = "https://mapping.gleif.org/api/v2/isin-lei/latest"
GLEIF_LATEST = "https://goldencopy.gleif.org/api/v2/golden-copies/publishes/latest"
csv.field_size_limit(10 ** 9)


def _latest_debt(files):
    """files: [(name, link)] -> (date, [links]) לסט FULINS_D השלם האחרון."""
    by = defaultdict(lambda: {"n": 0, "parts": {}})
    for name, link in files:
        m = src_firds.FILE_RX.match(name or "")
        if m and m.group(1) == "D":
            d = by[m.group(2)]
            d["n"] = int(m.group(4))
            d["parts"][int(m.group(3))] = link
    for date in sorted(by, reverse=True):
        if len(by[date]["parts"]) == by[date]["n"]:
            return date, [by[date]["parts"][i] for i in sorted(by[date]["parts"])]
    raise RuntimeError(f"no complete FULINS_D set among {sorted(by)}")


def list_esma():
    f = src_firds._since()
    r = get(src_firds.ESMA_FILES, params={"q": "*", "fq": f"publication_date:[{f}T00:00:00Z TO {TODAY}T23:59:59Z]",
                                          "wt": "json", "start": 0, "rows": 2000})
    return _latest_debt([(d.get("file_name"), d.get("download_link")) for d in r.json()["response"]["docs"]])


def list_fca():
    f = src_firds._since()
    r = get(src_firds.FCA_FILES, params={"q": f"((file_type:FULINS) AND (publication_date:[{f} TO {TODAY}]))",
                                         "from": 0, "size": 2000})
    src = [h.get("_source", {}) for h in r.json().get("hits", {}).get("hits", [])]
    return _latest_debt([(d.get("file_name"), d.get("download_link")) for d in src])


def parse_debt(content, out, reg):
    """מוסיף ל-out: isin -> [lei, cfi, ccy, maturity, short_name, reg]. ESMA קודם; FCA משלים ISIN חסר."""
    rows = kept = 0
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for member in z.namelist():
            with z.open(member) as f:
                for _, el in iterparse(f, events=("end",)):
                    if src_firds._local(el.tag) != "RefData":
                        continue
                    rows += 1
                    g, lei, mat = {}, None, None
                    for part in el:
                        p = src_firds._local(part.tag)
                        if p == "FinInstrmGnlAttrbts":
                            g = {src_firds._local(c.tag): (c.text or "").strip() for c in part}
                        elif p == "Issr":
                            lei = (part.text or "").strip()
                        elif p == "DebtInstrmAttrbts":
                            for c in part:
                                if src_firds._local(c.tag) == "MtrtyDt":
                                    mat = (c.text or "").strip()[:10]
                    el.clear()
                    isin, cfi = g.get("Id"), g.get("ClssfctnTp") or ""
                    if not isin or not cfi.startswith("D") or cfi[:2] in SKIP_CFI2:
                        continue
                    # אותו ISIN מדווח ע"י כל זירה בנפרד; חלק מהזירות (MarketAxess, Bloomberg Trading Facility...)
                    # רושמות את ה-LEI שלהן כ"מנפיק" - אוספים את כל ה-LEI-ים ובוחרים אחר כך (choose_issuer)
                    a = out.get(isin)
                    if a is None:
                        a = out[isin] = [Counter(), cfi, g.get("NtnlCcy") or "", mat or "", (g.get("ShrtNm") or "")[:60], reg]
                        kept += 1
                    if lei:
                        a[0][lei] += 1
    return rows, kept


# מפעילי זירות מסחר ומתווכים שמופיעים בשדה המנפיק במקום המנפיק עצמו (נמצא בריצה הראשונה: ~5,500 ISIN).
# VENUE_STRONG - אף פעם לא מנפיק; VENUE_OPERATOR - מפעילי בורסות שגם מנפיקים אג"ח משלהם (Deutsche Börse AG,
# Euronext N.V., Nasdaq Inc.), ולכן נחשבים זירה רק כשה-LEI מופיע כמנפיק של VENUE_MIN מכשירים ומעלה.
VENUE_STRONG = re.compile(r"trading\s+facility|marketaxess|tp\s+icap|liquidnet|tradeweb|wertpapierb[öo]rse|"
                          r"^gfi\s+securities|^bgc\s|\bmtf\b|^tradition\b|^tullett\b|^aquis\b|^turquoise\b", re.I)
VENUE_OPERATOR = re.compile(r"stock\s+exchange|b[öo]rse\s+aktiengesellschaft|^euronext\b|^nasdaq\b|"
                            r"intercontinental\s+exchange|^cboe\b|^bloomberg\b|^ice\s", re.I)
VENUE_MIN = 40


def venue_leis(bonds, names):
    n = Counter(l for v in bonds.values() for l in v[0])
    out = set()
    for lei, cnt in n.items():
        nm = (names.get(lei) or {}).get("name") or ""
        if VENUE_STRONG.search(nm) or (VENUE_OPERATOR.search(nm) and cnt >= VENUE_MIN):
            out.add(lei)
    return out


def choose_issuer(cands, venues):
    """הרוב מבין ה-LEI-ים שדווחו ל-ISIN, בלי מפעילי זירות. אם דווחה רק זירה - ריק (לא מנפיק שגוי)."""
    for lei, _ in cands.most_common():
        if lei not in venues:
            return lei
    return ""


def load_firds():
    out, meta = {}, {}
    for reg, lister in (("ESMA", list_esma), ("FCA", list_fca)):
        try:
            date, links = lister()
        except Exception as e:  # noqa: BLE001 - רגולטור אחד שנכשל לא מפיל את השני
            log(f"bonds {reg}: listing failed {e!r}")
            continue
        meta[reg] = {"date": date, "files": len(links)}
        for link in links:
            t = time.monotonic()
            content = get(link, timeout=900).content
            n, k = parse_debt(content, out, reg)
            log(f"bonds {reg}: {link.rsplit('/', 1)[-1]} {len(content) / 1e6:.0f}MB rows={n} kept={k} "
                f"total={len(out)} {time.monotonic() - t:.0f}s")
    return out, meta


# ------------------------------------------------------------------ GLEIF golden copy

def _urls(obj, acc):
    if isinstance(obj, dict):
        for v in obj.values():
            _urls(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _urls(v, acc)
    elif isinstance(obj, str) and obj.startswith("http"):
        acc.append(obj)
    return acc


def gleif_files():
    """-> (lei2_csv_zip_url, rr_csv_zip_url) מתוך ה-golden copy האחרון."""
    urls = _urls(get(GLEIF_LATEST).json(), [])
    pick = lambda kind: next((u for u in urls if re.search(rf"[-_/]{kind}[-_/.]", u, re.I) and "csv" in u.lower()
                              and "delta" not in u.lower()), None)
    lei2, rr = pick("lei2"), pick("rr")
    log(f"gleif golden: lei2={lei2} rr={rr}")
    if not lei2 or not rr:
        raise RuntimeError(f"gleif golden copy urls not found among {urls[:20]}")
    return lei2, rr


def stream_csv(url):
    """מוריד zip עם CSV ומחזיר DictReader זורם (לקובץ הגדול נשמר על הדיסק, לא בזיכרון)."""
    path = "/tmp/" + re.sub(r"[^\w.]", "_", url.rsplit("/", 1)[-1])[:80]
    if not path.endswith(".zip"):
        path += ".zip"
    with get(url, timeout=1800, stream=True) as r:
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    log(f"gleif: downloaded {path} {os.path.getsize(path) / 1e6:.0f}MB")
    z = zipfile.ZipFile(path)
    name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
    return csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8", newline=""))


def load_parents(rr_url, need):
    """RR: start -> {direct, ultimate} (LEI) לקשרי איחוד דוחות פעילים."""
    par = {}
    for r in stream_csv(rr_url):
        s = r.get("Relationship.StartNode.NodeID")
        if s not in need:
            continue
        t = r.get("Relationship.RelationshipType")
        if r.get("Relationship.RelationshipStatus") not in (None, "", "ACTIVE"):
            continue
        if t == "IS_DIRECTLY_CONSOLIDATED_BY":
            par.setdefault(s, {})["direct"] = r.get("Relationship.EndNode.NodeID")
        elif t == "IS_ULTIMATELY_CONSOLIDATED_BY":
            par.setdefault(s, {})["ultimate"] = r.get("Relationship.EndNode.NodeID")
    return par


def load_entities(lei2_url, need):
    ent = {}
    for r in stream_csv(lei2_url):
        lei = r.get("LEI")
        if lei not in need:
            continue
        ent[lei] = {"name": r.get("Entity.LegalName"), "country": r.get("Entity.LegalAddress.Country"),
                    "hq_country": r.get("Entity.HeadquartersAddress.Country"),
                    "ra": r.get("Entity.RegistrationAuthority.RegistrationAuthorityID"),
                    "reg_no": r.get("Entity.RegistrationAuthority.RegistrationAuthorityEntityID"),
                    "category": r.get("Entity.EntityCategory"), "status": r.get("Entity.EntityStatus"),
                    "legal_form": r.get("Entity.LegalForm.EntityLegalFormCode")}
    return ent


def _gz_json(path, obj):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def site_shard(lei):
    """מנפיק -> קובץ (64 קבצים), אותו חישוב בדף (Revach: securities-world-bonds.html)."""
    return int(hashlib.sha1(lei.encode()).hexdigest()[:8], 16) % 64


def write_site(bonds, ent, parents, leis, stats):
    """קבצים לדף האתר (נטענים ישירות מ-raw.githubusercontent, gzip):
    site/issuers.json.gz       - [lei, שם, מדינה, מס' מכשירים, שם חברת אם סופית, LEI חברת אם סופית, ישירה, מתוכם מובנים]
    site/lei/<0-63>.json.gz    - lei -> [[isin, cfi, ccy, maturity, short], ...]
    site/isin/<קידומת>.json.gz - isin -> [lei, cfi, ccy, maturity, short]; site/isin_index.json - רשימת הקידומות
                                 (4 תווים, ארוכה יותר כשיש יותר מ-ISIN_SHARD_MAX) - הדף בוחר את הקידומת הארוכה המתאימה
    site/meta.json             - תאריכים וספירות"""
    base = os.path.join(OUT, "site")
    for sub in ("lei", "isin"):
        os.makedirs(os.path.join(base, sub), exist_ok=True)
        for f in os.listdir(os.path.join(base, sub)):
            os.remove(os.path.join(base, sub, f))
    n = Counter(v[0] for v in bonds.values() if v[0])
    ns = Counter(v[0] for v in bonds.values() if v[0] and v[1][:2] in STRUCT_CFI2)
    rows = []
    for lei in sorted(leis):
        e, p = ent.get(lei) or {}, parents.get(lei) or {}
        u, d = p.get("ultimate"), p.get("direct")
        rows.append([lei, e.get("name"), e.get("country"), n[lei], (ent.get(u) or {}).get("name") if u else None, u,
                     (ent.get(d) or {}).get("name") if d and d != u else None, ns[lei]])
    _gz_json(os.path.join(base, "issuers.json.gz"), rows)
    by_lei = defaultdict(dict)
    for isin, v in bonds.items():
        if v[0]:
            by_lei[site_shard(v[0])].setdefault(v[0], []).append([isin] + v[1:5])
    for k, d in by_lei.items():
        for lei, lst in d.items():
            # מנפיק עם עשרות אלפי תעודות (SG Issuer וכו'): בדף עד LEI_CAP לכל סוג; חיפוש ISIN מכסה הכל
            # בתוקף קודם (פדיון קרוב), ניירות שמועד הפדיון שלהם עבר בסוף - שלא יתפסו את המכסה
            lst.sort(key=lambda r: (bool(r[3]) and r[3] < TODAY, r[3] or "9999", r[0]))
            st = [r for r in lst if r[1][:2] in STRUCT_CFI2]
            bd = [r for r in lst if r[1][:2] not in STRUCT_CFI2]
            d[lei] = bd[:LEI_CAP] + st[:LEI_CAP]
        _gz_json(os.path.join(base, "lei", f"{k}.json.gz"), d)
    # ISIN: קובץ לכל קידומת; קידומת עם יותר מ-ISIN_SHARD_MAX מתפצלת לקידומת ארוכה יותר (DE00 -> DE0001...)
    prefixes = []

    def write_isins(prefix, isins):
        if len(isins) > ISIN_SHARD_MAX and len(prefix) < 10:
            sub = defaultdict(list)
            for i in isins:
                sub[i[:len(prefix) + 1]].append(i)
            for p2, lst in sub.items():
                write_isins(p2, lst)
            return
        _gz_json(os.path.join(base, "isin", f"{prefix}.json.gz"), {i: [bonds[i][0]] + bonds[i][1:6] for i in isins})
        prefixes.append(prefix)

    by4 = defaultdict(list)
    for isin in bonds:
        by4[isin[:4]].append(isin)
    for p4, lst in by4.items():
        write_isins(p4, lst)
    json.dump(sorted(prefixes), open(os.path.join(base, "isin_index.json"), "w", encoding="utf-8"))
    by_isin = prefixes
    json.dump({"generated_at": stats["generated_at"], "firds": stats["firds"], "isins": stats["isins"],
               "issuers": stats["issuers"], "no_issuer": stats["no_issuer"],
               "issuer_from_mapping": stats["issuer_from_mapping"], "firds_vs_mapping": stats["firds_vs_mapping"],
               "structured": sum(1 for v in bonds.values() if v[1][:2] in STRUCT_CFI2)},
              open(os.path.join(base, "meta.json"), "w", encoding="utf-8"))
    log(f"site: {len(rows)} issuers, {len(by_lei)} lei shards, {len(by_isin)} isin shards")


def load_isin_map(isins):
    """GLEIF ISIN-LEI mapping (ANNA - סוכנויות המספור שהקצו את ה-ISIN, יחד עם GLEIF): isin -> lei של המנפיק.
    המקור הסמכותי למנפיק (מי שביקש את הקוד), בלי זירות מסחר בשדה המנפיק. נשמרים רק ISIN-ים מהמאגר."""
    urls = _urls(get(ISIN_MAP_LATEST).json(), [])
    link = next((u for u in urls if "download" in u.lower() or u.lower().endswith(".zip")), None)
    log(f"isin-lei mapping: {link}")
    if not link:
        raise RuntimeError(f"isin-lei mapping link not found among {urls[:10]}")
    out, multi, rows = {}, 0, 0
    for r in stream_csv(link):
        rows += 1
        isin, lei = (r.get("ISIN") or "").strip(), (r.get("LEI") or "").strip()
        if isin in isins and lei:
            if isin in out and out[isin] != lei:
                multi += 1  # ISIN עם יותר מ-LEI אחד במיפוי - נשאר הראשון
                continue
            out[isin] = lei
    log(f"isin-lei mapping: {rows} rows, {len(out)} of our ISINs mapped, {multi} with more than one LEI")
    return out


def main():
    os.makedirs(os.path.join(OUT, "isin"), exist_ok=True)
    bonds, meta = load_firds()
    if len(bonds) < 50000:
        raise RuntimeError(f"only {len(bonds)} debt ISINs - not overwriting")
    # המנפיק: קודם מיפוי ISIN-LEI הרשמי (סוכנות המספור), ורק אם אין בו - FIRDS (רוב הדיווחים, בלי זירות מסחר)
    try:
        imap = load_isin_map(set(bonds))
    except Exception as e:  # noqa: BLE001 - בלי המיפוי נשארים עם FIRDS בלבד (ומסומן בסטטיסטיקה)
        log(f"isin-lei mapping failed: {e!r} - FIRDS only")
        imap = {}
    cand_leis = {l for v in bonds.values() for l in v[0]} | set(imap.values())
    lei2_url, rr_url = gleif_files()
    names = load_entities(lei2_url, cand_leis)  # שמות לזיהוי מפעילי זירות
    venues = venue_leis(bonds, names)
    log(f"bonds: trading-venue LEIs reported as issuer: {sorted((names.get(l) or {}).get('name') or l for l in venues)}")
    venue_hits = both = agree = 0
    for isin, v in bonds.items():
        top = v[0].most_common(1)[0][0] if v[0] else ""
        firds = choose_issuer(v[0], venues)
        venue_hits += bool(top) and firds != top
        m = imap.get(isin)
        if m and firds:
            both += 1
            agree += m == firds
        v[0] = m or firds
        v[5] = "m" if m else ("f" if firds else "")   # מקור המנפיק: m = מיפוי ISIN-LEI, f = FIRDS
    log(f"bonds: issuer from mapping {sum(1 for v in bonds.values() if v[5] == 'm')}, from FIRDS "
        f"{sum(1 for v in bonds.values() if v[5] == 'f')}, none {sum(1 for v in bonds.values() if not v[0])}; "
        f"FIRDS vs mapping agree {agree}/{both}; venue fixed in FIRDS {venue_hits}")
    by_cc = defaultdict(list)
    for isin, v in bonds.items():
        by_cc[isin[:2]].append([isin] + v[:6])
    for cc, rows in by_cc.items():
        rows.sort()
        with gzip.open(os.path.join(OUT, "isin", f"{cc}.csv.gz"), "wt", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["isin", "lei", "cfi", "ccy", "maturity", "short_name", "issuer_source"])
            w.writerows(rows)
    leis = {v[0] for v in bonds.values() if v[0]}
    log(f"bonds: {len(bonds)} ISINs, {len(leis)} issuer LEIs, {len(by_cc)} ISIN prefixes")

    parents = load_parents(rr_url, leis)
    need = leis | {p for d in parents.values() for p in d.values() if p}
    ent = load_entities(lei2_url, need)
    with open(os.path.join(OUT, "issuers.jsonl"), "w", encoding="utf-8") as f:
        for lei in sorted(leis):
            e = dict(ent.get(lei) or {"missing": True})
            for k in ("direct", "ultimate"):
                p = (parents.get(lei) or {}).get(k)
                if p:
                    e[k] = {"lei": p, "name": (ent.get(p) or {}).get("name"), "country": (ent.get(p) or {}).get("country")}
            f.write(json.dumps({"lei": lei, **e}, ensure_ascii=False) + "\n")
    cfi2 = Counter(v[1][:2] for v in bonds.values())
    stats = {"generated_at": NOW_ISO, "firds": meta, "isins": len(bonds), "issuers": len(leis),
             "venue_issuer_fixed": venue_hits, "no_issuer": sum(1 for v in bonds.values() if not v[0]),
             "issuer_from_mapping": sum(1 for v in bonds.values() if v[5] == "m"),
             "issuer_from_firds": sum(1 for v in bonds.values() if v[5] == "f"),
             "firds_vs_mapping": {"both": both, "agree": agree, "agree_pct": round(100 * agree / both, 2) if both else None},
             "issuers_in_gleif": sum(1 for l in leis if l in ent),
             "with_direct_parent": sum(1 for l in leis if (parents.get(l) or {}).get("direct")),
             "with_ultimate_parent": sum(1 for l in leis if (parents.get(l) or {}).get("ultimate")),
             "by_cfi2": dict(cfi2.most_common()), "by_isin_prefix": dict(Counter({k: len(v) for k, v in by_cc.items()}).most_common(40))}
    json.dump(stats, open(os.path.join(OUT, "stats.json"), "w", encoding="utf-8"), indent=1)
    write_site(bonds, ent, parents, leis, stats)
    log(json.dumps(stats)[:1500])


if __name__ == "__main__":
    main()
