"""סריקה מלאה של API הנגזרים הרשמי של הבורסה (TASE) - בונה מיפוי Name(סימול
האופציה)->AssetName(שם נכס הבסיס הרשמי) לכל ~7500 הנגזרים, כדי לפענח את
קודי-הקיצור העבריים שמופיעים בדוחות MASLULIM (בזן/ברס/פנק/פרן שנשארו
לא-ממופים ב-option_ticker_parse.py + לאמת מחדש את הידועים).

הרצה: python scripts/probe_tase_derivatives.py
"""
import json
import time
from pathlib import Path

import requests

URL = "https://api.tase.co.il/api/derivatives/all"
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "he-IL",
    "content-type": "application/json;charset=UTF-8",
    "referer": "https://market.tase.co.il/",
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"),
    "origin": "https://market.tase.co.il",
}
OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)
PAGE_SIZE = 30
MAX_PAGES = 260  # ~7492/30


def fetch(page):
    r = requests.post(URL, headers=HEADERS,
                       json={"qType": 1, "dType": 1, "TotalRec": 1, "pageNum": page, "oId": "", "lang": "0"},
                       timeout=30)
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except Exception:
        return None


def main():
    name_to_asset = {}
    total_rec = None
    for page in range(1, MAX_PAGES + 1):
        data = fetch(page)
        if not data:
            print(f"page {page}: FAIL")
            continue
        total_rec = data.get("TotalRec")
        items = data.get("Items", [])
        if not items:
            print(f"page {page}: empty, stopping")
            break
        for it in items:
            name = it.get("Name")
            asset = it.get("AssetName")
            if name:
                name_to_asset[name] = asset
        if page % 20 == 0:
            print(f"page {page}: {len(items)} items, running total {len(name_to_asset)}")
        time.sleep(0.15)

    print(f"\nTotalRec (server): {total_rec}, collected {len(name_to_asset)} Name->AssetName mappings")
    (OUT / "tase_deriv_full_map.json").write_text(
        json.dumps(name_to_asset, ensure_ascii=False), encoding="utf-8")

    # החלוצים שחיפשנו במפורש
    targets = ["בזן", "ברס", "פנק", "פרן", "כלל", "בזק", "דסק", "ת35", "35ת"]
    print("\n--- דוגמאות לכל קוד-יעד ---")
    for t in targets:
        matches = [(n, a) for n, a in name_to_asset.items() if n.endswith(f"-{t}")]
        print(f"{t}: {len(matches)} matches, sample: {matches[:2]}")


if __name__ == "__main__":
    main()
