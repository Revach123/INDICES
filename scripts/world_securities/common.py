"""תשתית משותפת למאגר ניירות הערך העולמי (אירופה, בריטניה, שווייץ, יפן, קנדה).

עקרונות (כמו מאגרי ת"א וארה"ב בפרויקט Revach):
  - מקורות רשמיים בלבד (רגולטור / בורסה / GLEIF / ISO), בלי ניחוש משמות.
  - לא מוחקים שורות: נייר שנעלם מקבל removed_at; ערך קיים לא-ריק לא נדרס בריק.
  - כל שוק "הכל או כלום": אם המקור של שוק נכשל - שורות השוק נשארות כמו בריצה הקודמת.
"""
import csv
import datetime
import io
import json
import os
import time

import requests

NOW = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
TODAY = NOW.date().isoformat()
NOW_ISO = NOW.isoformat()
OUT_DIR = os.environ.get("WORLD_OUT_DIR", "data/world_securities")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA})


def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def http(method, url, retries=4, timeout=120, ok_404=False, **kw):
    last = None
    for attempt in range(retries):
        try:
            r = SESSION.request(method, url, timeout=timeout, **kw)
            if r.status_code == 404 and ok_404:
                return None
            if r.status_code == 429 or r.status_code >= 500:
                last = f"HTTP {r.status_code}"
                time.sleep(5 * (attempt + 1) + (30 if r.status_code == 429 else 0))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = repr(e)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{method} {url} failed: {last}")


def get(url, **kw):
    return http("GET", url, **kw)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, obj, compact=True):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        if compact:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)


def count(rows, key):
    out = {}
    for r in rows:
        k = r.get(key) if not callable(key) else key(r)
        k = k if k not in (None, "") else "—"
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


# ------------------------------------------------------------------ ISO 10383 (MIC)

MIC_URL = "https://www.iso20022.org/sites/default/files/ISO10383_MIC/ISO10383_MIC_NewFormat.csv"


def load_mics():
    """MIC -> {name, oprt, cc, cat, city, website, status, acronym}. cat: RMKT שוק מוסדר, MLTF MTF..."""
    text = get(MIC_URL).content.decode("utf-8-sig", "replace")
    mics = {}
    for r in csv.DictReader(io.StringIO(text)):
        r = {(k or "").strip().upper(): (v or "").strip() for k, v in r.items()}
        mic = r.get("MIC")
        if not mic:
            continue
        mics[mic] = {
            "name": r.get("NAME-INSTITUTION DESCRIPTION") or r.get("MARKET NAME-INSTITUTION DESCRIPTION"),
            "oprt": r.get("OPERATING MIC") or mic,
            "cc": r.get("ISO COUNTRY CODE (ISO 3166)"),
            "cat": r.get("MARKET_CAT_CODE") or r.get("MARKET CATEGORY CODE"),
            "city": r.get("CITY"), "acronym": r.get("ACRONYM"), "status": r.get("STATUS"),
            "website": r.get("WEBSITE"),
        }
    if len(mics) < 1000:
        raise RuntimeError(f"MIC list too small: {len(mics)}")
    # MIC תפעולי (OPRT) מסומן לרוב NSPD ("לא מוגדר") - סוג השוק מופיע רק על הסגמנטים שלו.
    # FIRDS מדווח לפעמים את ה-MIC התפעולי (XPAR, XLON, XMIL), אז הוא מקבל את סוג הסגמנטים:
    # RMKT אם יש לו סגמנט שוק מוסדר פעיל, אחרת MLTF אם יש סגמנט MTF.
    seg_cats = {}
    for mic, m in mics.items():
        if m["oprt"] != mic and m.get("status") == "ACTIVE":
            seg_cats.setdefault(m["oprt"], set()).add(m.get("cat"))
    for mic, m in mics.items():
        if m["oprt"] == mic and m.get("cat") not in ("RMKT", "MLTF"):
            cats = seg_cats.get(mic, set())
            eff = "RMKT" if "RMKT" in cats else "MLTF" if "MLTF" in cats else None
            if eff:
                m["cat_raw"], m["cat"] = m.get("cat"), eff
    return mics


# ------------------------------------------------------------------ ISO 10962 (CFI)
# סוג הנייר = שתי האותיות הראשונות של קוד ה-CFI הרשמי שהרגולטור מפרסם לכל נייר.

CFI_TYPES = {
    "ES": ("Common Stock", "מניה רגילה"),
    "EP": ("Preferred Stock", "מניית בכורה"),
    "EC": ("Convertible Common", "מניה רגילה המירה"),
    "EF": ("Convertible Preferred", "מניית בכורה המירה"),
    "EL": ("Limited Partnership", "יחידת שותפות"),
    "ED": ("Depositary Receipt", "תעודת פיקדון (DR)"),
    "EY": ("Structured (Participation)", "מוצר מובנה"),
    "EM": ("Other Equity", "מניה - אחר"),
    "CE": ("ETF", "קרן סל (ETF)"),
    "CI": ("Investment Fund", "קרן השקעה"),
    "CB": ("REIT", "קרן ריט (REIT)"),
    "CH": ("Hedge Fund", "קרן גידור"),
    "CF": ("Fund of Funds", "קרן של קרנות"),
    "CP": ("Private Equity Fund", "קרן הון פרטי"),
    "CS": ("Pension Fund", "קרן פנסיה"),
    "CM": ("Other Fund", "קרן - אחר"),
}

# קטגוריה ראשית לדף (כמו בדפי ת"א/ארה"ב)
CATEGORY_BY_TYPE = {
    "Common Stock": "stocks", "Preferred Stock": "stocks", "Convertible Common": "stocks",
    "Convertible Preferred": "stocks", "Limited Partnership": "stocks", "Other Equity": "stocks",
    "REIT Stock": "stocks", "Depositary Receipt": "dr",
    "ETF": "etf", "ETN": "etf", "ETF/ETN": "etf", "ETC": "etf",
    "Investment Fund": "funds", "REIT": "funds", "Hedge Fund": "funds", "Fund of Funds": "funds",
    "Private Equity Fund": "funds", "Pension Fund": "funds", "Other Fund": "funds", "Infrastructure Fund": "funds",
    "Real Estate Fund": "funds", "Participation Certificate": "stocks",
    "Warrant": "other", "Right": "other", "Unit": "other", "Debenture": "other", "Other": "other",
}


# ------------------------------------------------------------------ GLEIF

GLEIF_URL = "https://api.gleif.org/api/v1/lei-records"
GLEIF_REFRESH_DAYS = 30


def gleif_enrich(leis, cache, budget_sec=1200):
    """cache: lei -> {name, country, hq_country, city, hq_city, status, category, legal_form, d}."""
    cut = (NOW - datetime.timedelta(days=GLEIF_REFRESH_DAYS)).isoformat()
    todo = sorted(l for l in leis if l and (cache.get(l) or {}).get("d", "") < cut)
    log(f"gleif: {len(todo)} LEIs to fetch ({len(leis)} total)")
    start, done = time.monotonic(), 0
    for i in range(0, len(todo), 100):
        if time.monotonic() - start > budget_sec:
            log(f"gleif: budget reached, {len(todo) - i} deferred")
            break
        chunk = todo[i:i + 100]
        try:
            r = get(GLEIF_URL, params={"filter[lei]": ",".join(chunk), "page[size]": 200})
        except Exception as e:  # noqa: BLE001
            log(f"gleif: request failed {e!r} - stopping")
            break
        seen = set()
        for x in r.json().get("data", []):
            a = x.get("attributes", {})
            ent = a.get("entity", {})
            la, hq = ent.get("legalAddress") or {}, ent.get("headquartersAddress") or {}
            cache[x["id"]] = {
                "name": (ent.get("legalName") or {}).get("name"),
                "country": la.get("country"), "city": la.get("city"),
                "hq_country": hq.get("country"), "hq_city": hq.get("city"),
                "jurisdiction": ent.get("jurisdiction"),
                "status": ent.get("status"), "category": ent.get("category"),
                "legal_form": (ent.get("legalForm") or {}).get("id"),
                "reg_status": (a.get("registration") or {}).get("status"),
                "d": NOW_ISO,
            }
            seen.add(x["id"])
        for l in chunk:
            if l not in seen:
                cache[l] = {"missing": True, "d": NOW_ISO}
        done += len(chunk)
        time.sleep(1.1)   # GLEIF: 60 בקשות לדקה
    log(f"gleif: fetched {done}")


# ------------------------------------------------------------------ OpenFIGI (לפי MIC)

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
OPENFIGI_KEY = os.environ.get("OPENFIGI_API_KEY", "").strip()
OPENFIGI_JOBS = 100 if OPENFIGI_KEY else 10
OPENFIGI_GAP = 0.25 if OPENFIGI_KEY else 2.45     # 25 בקשות/6ש' עם מפתח, 25/דקה בלי
FIGI_RECHECK_DAYS = 60
FIGI_MISS_RETRY_DAYS = 14


class Figi:
    def __init__(self):
        self.next_at = 0.0

    def map(self, jobs):
        h = {"Content-Type": "application/json"}
        if OPENFIGI_KEY:
            h["X-OPENFIGI-APIKEY"] = OPENFIGI_KEY
        for attempt in range(6):
            wait = self.next_at - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self.next_at = time.monotonic() + OPENFIGI_GAP
            try:
                r = SESSION.post(OPENFIGI_URL, json=jobs, headers=h, timeout=60)
                if r.status_code == 429:
                    time.sleep(int(r.headers.get("ratelimit-reset") or 0) + 10 + 20 * attempt)
                    continue
                if r.status_code >= 500:
                    time.sleep(10)
                    continue
                r.raise_for_status()
                return r.json()
            except requests.RequestException:
                time.sleep(10)
        return None


def figi_lookup(requests_by_key, cache, budget_sec):
    """requests_by_key: key -> job (dict לבקשת OpenFIGI). cache: key -> {job, data|None, d}.
    בודק רק מה שלא נבדק / ישן / שהבקשה השתנתה. מחזיר מספר שנבדקו."""
    now = NOW_ISO
    ok_cut = (NOW - datetime.timedelta(days=FIGI_RECHECK_DAYS)).isoformat()
    miss_cut = (NOW - datetime.timedelta(days=FIGI_MISS_RETRY_DAYS)).isoformat()
    todo = []
    for k, job in requests_by_key.items():
        c = cache.get(k)
        if c and c.get("job") == job and c.get("d", "") >= (ok_cut if c.get("data") else miss_cut):
            continue
        todo.append(k)
    todo.sort(key=lambda k: k in cache)   # קודם מה שלא נבדק מעולם
    log(f"openfigi: {len(todo)} lookups ({'with' if OPENFIGI_KEY else 'without'} API key, budget {budget_sec}s)")
    client, start, done = Figi(), time.monotonic(), 0
    for i in range(0, len(todo), OPENFIGI_JOBS):
        if time.monotonic() - start > budget_sec:
            log(f"openfigi: budget reached - {len(todo) - i} deferred to next run")
            break
        chunk = todo[i:i + OPENFIGI_JOBS]
        res = client.map([requests_by_key[k] for k in chunk])
        if res is None:
            log("openfigi: unavailable - stopping")
            break
        for k, r in zip(chunk, res):
            if r.get("error") and "No identifier found" not in r["error"]:
                continue
            data = [{f: d.get(f) for f in ("figi", "compositeFIGI", "shareClassFIGI", "ticker", "exchCode", "name",
                                           "securityType", "securityType2", "marketSector")}
                    for d in (r.get("data") or [])]
            cache[k] = {"job": requests_by_key[k], "data": data or None, "d": now}
            done += 1
        if (i // OPENFIGI_JOBS) % 100 == 0:
            log(f"openfigi: {done}/{len(todo)}")
    log(f"openfigi: looked up {done}")
    return done


def dominant_exch_codes(cache):
    """לכל MIC - ה-exchCode של Bloomberg שמופיע ברוב הרשומות שהוחזרו עבורו (נגזר מהנתונים,
    לא טבלה ידנית). משמש לבחירת קווי המסחר הראשיים כש-OpenFIGI מחזיר כמה (XLON -> LN)."""
    per = {}
    for c in cache.values():
        mic = (c.get("job") or {}).get("micCode")
        for d in c.get("data") or []:
            per.setdefault(mic, {}).setdefault(d.get("exchCode"), 0)
            per[mic][d.get("exchCode")] += 1
    return {mic: max(v, key=v.get) for mic, v in per.items() if v}


def figi_pick(entry, dominant):
    """(ticker, tickers, figi, share_class_figi, security_type) מרשומת מטמון.
    רק קווים של ה-exchCode הדומיננטי ל-MIC. ticker/figi - רק אם חד-משמעי."""
    if not entry or not entry.get("data"):
        return None
    mic = (entry.get("job") or {}).get("micCode")
    rows = entry["data"]
    dom = dominant.get(mic)
    main = [d for d in rows if d.get("exchCode") == dom] or rows
    tickers = sorted({d["ticker"] for d in main if d.get("ticker")})
    comps = {d.get("compositeFIGI") or d.get("figi") for d in main}
    shares = {d.get("shareClassFIGI") for d in rows if d.get("shareClassFIGI")}
    types = {d.get("securityType") for d in main if d.get("securityType")}
    return {
        "ticker": tickers[0] if len(tickers) == 1 else None,
        "tickers": tickers,
        "figi": next(iter(comps)) if len(comps) == 1 else None,
        "share_class_figi": next(iter(shares)) if len(shares) == 1 else None,
        "figi_security_type": next(iter(types)) if len(types) == 1 else None,
        "figi_exch_code": dom,
    }


# ------------------------------------------------------------------ מיזוג

def merge_row(prev, new, recompute=()):
    """ערך קיים לא-ריק לא נדרס בריק; שדות ב-recompute נקבעים מחדש תמיד."""
    out = dict(prev or {})
    for k, v in new.items():
        if k in recompute:
            out[k] = v
        elif v is None or v == "" or v == []:
            out.setdefault(k, None)
        else:
            out[k] = v
    return out
