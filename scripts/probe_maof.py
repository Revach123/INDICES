"""בדיקת היתכנות: מקור לרשימת מניות-מעוף (אופציות בודדות על TASE) + קודי
הקיצור העבריים שמופיעים בסימול האופציה (למשל "כלל"/"בזק"/"דסק"/"בזן"/"פנק"/
"ברס") - נדרש כדי לפענח שורות אופציות ב-MASLULIM (ר' שם, שם נייר ערך
בגיליונות אופציות/לא סחיר אופציות, פורמט TASE MAOF: C023000M608-כלל).

הרצה: python scripts/probe_maof.py
"""
import json
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)

CANDIDATES = {
    "wikipedia_he_maof": "https://he.wikipedia.org/wiki/%D7%A9%D7%95%D7%A7_%D7%94%D7%9E%D7%A2%D7%95%22%D7%A3",
    "globes_optionlist": "https://www.globes.co.il/portal/optionlist/?TypeID=15",
    "tase_maof_underlyings": "https://api.tase.co.il/api/maoflist/underlyings",
    "tase_derivatives_list": "https://api.tase.co.il/api/content/maoflist/getmaoflist",
    "tase_main": "https://www.tase.co.il/he/market_data/derivatives",
    "wikipedia_he_ta35": "https://he.wikipedia.org/wiki/%D7%AA%D7%9C_%D7%90%D7%91%D7%99%D7%91_35",
}


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "he,en;q=0.8"})
    report = {}
    for name, url in CANDIDATES.items():
        try:
            r = session.get(url, timeout=15)
            report[name] = {"status": r.status_code, "len": len(r.content), "ct": r.headers.get("content-type")}
            if r.status_code == 200 and "json" in (r.headers.get("content-type") or ""):
                report[name]["sample"] = r.text[:2000]
            elif r.status_code == 200:
                (OUT / f"{name}.html").write_bytes(r.content[:500000])
        except Exception as e:
            report[name] = {"error": repr(e)}
    txt = json.dumps(report, ensure_ascii=False, indent=2)
    print(txt)
    (OUT / "probe_maof.json").write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
