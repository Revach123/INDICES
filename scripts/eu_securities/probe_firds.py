"""בדיקת היתכנות למאגר ניירות ערך אירופיים - מקורות רשמיים בלבד:

  ESMA FIRDS  - מאגר הייחוס של הרגולטור האירופי: כל נייר שנסחר באיחוד (ISIN, CFI,
                LEI של המנפיק, זירות מסחר - MIC, ו-RlvntTradgVn = הזירה הרלוונטית)
  FCA FIRDS   - אותו פורמט מהרגולטור הבריטי (בריטניה מחוץ לאיחוד)
  GLEIF       - פרטי המנפיק לפי LEI
  ISO 10383   - רשימת קודי MIC (שם הבורסה, מדינה, RMKT = שוק מוסדר)

כותב סיכומים ל-probe_out/eu_*.json. הרצה: python scripts/eu_securities/probe_firds.py
"""
import collections
import datetime
import io
import json
import time
import zipfile
from pathlib import Path
from xml.etree.ElementTree import iterparse

import requests

OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (compatible; revach-securities-probe/1.0)"
S = requests.Session()
S.headers.update({"User-Agent": UA})
TODAY = datetime.date.today()
FROM = TODAY - datetime.timedelta(days=14)
REPORT = {}


def save(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def get(url, **kw):
    t = time.monotonic()
    r = S.get(url, timeout=kw.pop("timeout", 60), **kw)
    return r, round(time.monotonic() - t, 1)


def esma_files(core):
    url = (f"https://registers.esma.europa.eu/solr/{core}/select?q=*"
           f"&fq=publication_date:%5B{FROM}T00:00:00Z+TO+{TODAY}T23:59:59Z%5D&wt=json&start=0&rows=500")
    try:
        r, sec = get(url)
        info = {"url": url, "status": r.status_code, "sec": sec, "bytes": len(r.content)}
        if r.ok:
            docs = r.json().get("response", {}).get("docs", [])
            info["n_docs"] = len(docs)
            info["sample_docs"] = docs[:3]
            info["files"] = sorted({(d.get("file_name"), d.get("download_link"), d.get("file_type"),
                                     str(d.get("publication_date"))) for d in docs})
        else:
            info["head"] = r.text[:500]
        return info
    except Exception as e:  # noqa: BLE001
        return {"url": url, "error": repr(e)}


def fca_files():
    url = ("https://api.data.fca.org.uk/fca_data_firds_files?q=((file_type:FULINS)%20AND%20(publication_date:"
           f"%5B{FROM}%20TO%20{TODAY}%5D))&from=0&size=200&pretty=true")
    try:
        r, sec = get(url)
        info = {"url": url, "status": r.status_code, "sec": sec, "bytes": len(r.content)}
        if r.ok:
            hits = r.json().get("hits", {}).get("hits", [])
            src = [h.get("_source", {}) for h in hits]
            info["n"] = len(src)
            info["sample"] = src[:3]
            info["files"] = sorted({(d.get("file_name"), d.get("download_link"), str(d.get("publication_date")))
                                    for d in src})
        else:
            info["head"] = r.text[:500]
        return info
    except Exception as e:  # noqa: BLE001
        return {"url": url, "error": repr(e)}


def local(tag):
    return tag.rsplit("}", 1)[-1]


def parse_firds_zip(content, agg, stats):
    """FULINS zip -> XML (auth.017). מצטבר לפי ISIN."""
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for name in z.namelist():
            with z.open(name) as f:
                for ev, el in iterparse(f, events=("end",)):
                    if local(el.tag) != "RefData":
                        continue
                    rec = {"venues": set(), "issr_req": set()}
                    for part in el:
                        p = local(part.tag)
                        if p == "FinInstrmGnlAttrbts":
                            for c in part:
                                rec[local(c.tag)] = (c.text or "").strip()
                        elif p == "Issr":
                            rec["lei"] = (part.text or "").strip()
                        elif p == "TradgVnRltdAttrbts":
                            v = {local(c.tag): (c.text or "").strip() for c in part}
                            mic = v.get("Id")
                            term = v.get("TermntnDt")
                            if term and term[:10] < str(TODAY):
                                stats["terminated_rows"] += 1
                                continue
                            rec["venues"].add(mic)
                            if v.get("IssrReq") == "true":
                                rec["issr_req"].add(mic)
                        elif p == "TechAttrbts":
                            for c in part:
                                if local(c.tag) == "RlvntTradgVn":
                                    rec["rlvnt"] = (c.text or "").strip()
                                elif local(c.tag) == "RlvntCmptntAuthrty":
                                    rec["nca"] = (c.text or "").strip()
                    el.clear()
                    stats["rows"] += 1
                    isin = rec.get("Id")
                    if not isin:
                        continue
                    a = agg.get(isin)
                    if a is None:
                        a = agg[isin] = {"name": rec.get("FullNm"), "short": rec.get("ShrtNm"),
                                         "cfi": rec.get("ClssfctnTp"), "ccy": rec.get("NtnlCcy"),
                                         "lei": rec.get("lei"), "venues": set(), "issr_req": set(),
                                         "rlvnt": rec.get("rlvnt"), "nca": rec.get("nca")}
                    a["venues"] |= rec["venues"]
                    a["issr_req"] |= rec["issr_req"]
                    if rec.get("rlvnt"):
                        a["rlvnt"] = rec["rlvnt"]


def mic_list():
    urls = ["https://www.iso20022.org/sites/default/files/ISO10383_MIC/ISO10383_MIC.csv",
            "https://www.iso20022.org/sites/default/files/ISO10383_MIC/ISO10383_MIC_NewFormat.csv"]
    out = {}
    for u in urls:
        try:
            r, sec = get(u)
            out[u] = {"status": r.status_code, "sec": sec, "bytes": len(r.content), "head": r.text[:600]}
            if r.ok and len(r.content) > 10000:
                out["_content"] = r.content.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            out[u] = {"error": repr(e)}
    return out


def summarize(agg, mics, label):
    by_rlvnt = collections.Counter()
    by_cfi2 = collections.Counter()
    issuer_listed = 0
    rm_listed = 0
    for isin, a in agg.items():
        by_cfi2[(a["cfi"] or "??")[:2]] += 1
        by_rlvnt[a["rlvnt"] or "-"] += 1
        if a["issr_req"]:
            issuer_listed += 1
        if any(mics.get(m, {}).get("cat") == "RMKT" for m in a["venues"]):
            rm_listed += 1
    sample_keys = [k for k in agg if agg[k]["issr_req"]][:15]
    return {
        "label": label,
        "distinct_isins": len(agg),
        "with_issuer_request_venue": issuer_listed,
        "on_regulated_market": rm_listed,
        "with_lei": sum(1 for a in agg.values() if a["lei"]),
        "distinct_leis": len({a["lei"] for a in agg.values() if a["lei"]}),
        "by_cfi2": by_cfi2.most_common(),
        "by_relevant_venue_top60": [(m, n, mics.get(m, {}).get("name"), mics.get(m, {}).get("cc"))
                                    for m, n in by_rlvnt.most_common(60)],
        "isin_prefix_top30": collections.Counter(k[:2] for k in agg).most_common(30),
        "sample": {k: {**agg[k], "venues": sorted(agg[k]["venues"])[:12], "issr_req": sorted(agg[k]["issr_req"])}
                   for k in sample_keys},
        "known": {k: ({**agg[k], "venues": sorted(agg[k]["venues"])[:20], "issr_req": sorted(agg[k]["issr_req"])}
                      if k in agg else None)
                  for k in ("DE0007164600", "FR0000121014", "NL0010273215", "IE00B4L5Y983", "IE00B5BMR087",
                            "GB0005405286", "CH0038863350", "IT0003128367", "US0378331005", "IL0006290147")},
    }


def parse_mics(text):
    import csv
    mics = {}
    rows = list(csv.DictReader(io.StringIO(text)))
    for r in rows:
        r = {(k or "").strip().upper(): (v or "").strip() for k, v in r.items()}
        mic = r.get("MIC")
        if mic:
            mics[mic] = {"name": r.get("MARKET NAME-INSTITUTION DESCRIPTION") or r.get("NAME-INSTITUTION DESCRIPTION"),
                         "cc": r.get("ISO COUNTRY CODE (ISO 3166)") or r.get("COUNTRY"),
                         "cat": r.get("MARKET CATEGORY CODE"), "oprt": r.get("OPERATING MIC"),
                         "status": r.get("STATUS")}
    return mics, (list(rows[0].keys()) if rows else [])


def process_category(files, cat, mics, label, max_files=20):
    """מוריד ומפרסר את קבצי FULINS של קטגוריה (E=מניות, C=קרנות) מהסט העדכני ביותר."""
    sel = [f for f in files if f[0] and f[0].startswith(f"FULINS_{cat}_")]
    if not sel:
        return {"label": label, "error": "no files"}
    latest = max(f[0].split("_")[2] for f in sel)
    sel = [f for f in sel if f[0].split("_")[2] == latest][:max_files]
    agg, stats = {}, collections.Counter()
    dl = []
    for name, link, *_ in sel:
        try:
            r, sec = get(link, timeout=600)
            dl.append({"file": name, "status": r.status_code, "mb": round(len(r.content) / 1e6, 1), "sec": sec})
            if r.ok:
                t = time.monotonic()
                parse_firds_zip(r.content, agg, stats)
                dl[-1]["parse_sec"] = round(time.monotonic() - t, 1)
        except Exception as e:  # noqa: BLE001
            dl.append({"file": name, "error": repr(e)})
    s = summarize(agg, mics, label)
    s["downloads"], s["stats"] = dl, dict(stats)
    return s


def gleif():
    url = ("https://api.gleif.org/api/v1/lei-records?filter%5Blei%5D="
           "529900D6BF99LW9R2E68,969500UP76J52A9OXU27&page%5Bsize%5D=200")
    try:
        r, sec = get(url)
        d = r.json() if r.ok else {}
        recs = [{"lei": x["id"], "name": x["attributes"]["entity"]["legalName"]["name"],
                 "country": x["attributes"]["entity"]["legalAddress"]["country"],
                 "hq": x["attributes"]["entity"]["headquartersAddress"]["country"],
                 "status": x["attributes"]["entity"]["status"]} for x in d.get("data", [])]
        return {"status": r.status_code, "sec": sec, "records": recs, "head": None if r.ok else r.text[:300]}
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)}


def main():
    REPORT["esma_firds_files"] = esma = esma_files("esma_registers_firds_files")
    REPORT["esma_fitrs_files"] = {k: v for k, v in esma_files("esma_registers_fitrs_files").items() if k != "files"}
    REPORT["fca_firds_files"] = fca = fca_files()
    REPORT["gleif"] = gleif()
    m = mic_list()
    content = m.pop("_content", None)
    REPORT["mic"] = m
    mics, cols = parse_mics(content) if content else ({}, [])
    REPORT["mic_parsed"] = {"n": len(mics), "columns": cols, "sample": dict(list(mics.items())[:5])}
    save("eu_probe_report.json", REPORT)

    if esma.get("files"):
        for cat, label in (("E", "esma_equities"), ("C", "esma_funds")):
            save(f"eu_{label}.json", process_category(esma["files"], cat, mics, label))
    if fca.get("files"):
        for cat, label in (("E", "fca_equities"), ("C", "fca_funds")):
            save(f"eu_{label}.json", process_category(fca["files"], cat, mics, label))
    save("eu_probe_report.json", REPORT)
    print(json.dumps(REPORT, ensure_ascii=False, indent=1, default=str)[:20000])


if __name__ == "__main__":
    main()
