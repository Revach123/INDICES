"""בדיקת היתכנות: מקור לרשימת מניות-מעוף (אופציות בודדות על TASE) + קודי
הקיצור העבריים שמופיעים בסימול האופציה (למשל "כלל"/"בזק"/"דסק"/"בזן"/"פנק"/
"ברס") - נדרש כדי לפענח שורות אופציות ב-MASLULIM (ר' שם, שם נייר ערך
בגיליונות אופציות/לא סחיר אופציות, פורמט TASE MAOF: C023000M608-כלל).

שלב 1 (זה): רק לשלוף טקסט קריא (לא HTML גולמי) מהמקורות שנמצאו נגישים
(Wikipedia, Globes) ולשמור לקובץ שנקרא כאן דרך raw.githubusercontent.com -
כדי לבדוק בפועל מה יש שם לפני בניית parser מובנה.

הרצה: python scripts/probe_maof.py
"""
import json
import re
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)

CANDIDATES = {
    "wikipedia_he_maof": "https://he.wikipedia.org/wiki/%D7%A9%D7%95%D7%A7_%D7%94%D7%9E%D7%A2%D7%95%22%D7%A3",
    "globes_optionlist": "https://www.globes.co.il/portal/optionlist/?TypeID=15",
}


def strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    text = re.sub(r"(?s)<[^>]+>", "\n", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "he,en;q=0.8"})
    for name, url in CANDIDATES.items():
        try:
            r = session.get(url, timeout=20)
            print(name, r.status_code, len(r.content))
            if r.status_code == 200:
                text = strip_html(r.text)
                (OUT / f"{name}.txt").write_text(text, encoding="utf-8")
        except Exception as e:
            print(name, "ERROR", repr(e))


if __name__ == "__main__":
    main()
