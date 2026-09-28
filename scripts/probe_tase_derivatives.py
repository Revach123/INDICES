"""API רשמי של הבורסה לניירות ערך (TASE) לרשימת נגזרים - נמסר ע"י המשתמש.
נסיונות קודמים ל-TASE (GET רגיל, headers/UA גנריים) קיבלו 403 גם דרך
GitHub Actions (ר' probe_maof.py) - מנסה כאן POST עם headers שמחקים בקשת
דפדפן אמיתית מ-market.tase.co.il (referrer/sec-fetch-*) שאולי עוקפת את
הגנת הבוט.

הרצה: python scripts/probe_tase_derivatives.py
"""
import json
from pathlib import Path

import requests

URL = "https://api.tase.co.il/api/derivatives/all"
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "he-IL",
    "content-type": "application/json;charset=UTF-8",
    "sec-ch-ua": "\"Chromium\";v=\"152\", \"Not?A_Brand\";v=\"24\", \"Google Chrome\";v=\"152\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "referer": "https://market.tase.co.il/",
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"),
    "origin": "https://market.tase.co.il",
}
BODY = {"qType": 1, "dType": 1, "TotalRec": 1, "pageNum": 1, "oId": "", "lang": "0"}
OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)


def main():
    r = requests.post(URL, headers=HEADERS, json=BODY, timeout=30)
    print("status:", r.status_code)
    print("content-type:", r.headers.get("content-type"))
    text = r.text
    (OUT / "tase_derivatives_all.txt").write_text(text[:200000], encoding="utf-8")
    print(text[:3000])


if __name__ == "__main__":
    main()
