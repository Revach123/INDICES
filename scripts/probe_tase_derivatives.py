"""בדיקה: האם TotalRec בגוף הבקשה שולט בגודל העמוד בפועל (נסיון קודם עם
TotalRec=1 תמיד החזיר 30 פריטים, כולם ת"א-35 - כנראה ממוינים לפי
AssetNumber ולא מפולטרים ע"י dType/qType). מנסה TotalRec=8000 וגם pageNum
גבוה יותר כדי להגיע למניות בודדות.
"""
import json
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


def fetch(body):
    r = requests.post(URL, headers=HEADERS, json=body, timeout=30)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:500]}


def main():
    results = {}

    # נסיון 1: TotalRec גדול
    status, data = fetch({"qType": 1, "dType": 1, "TotalRec": 8000, "pageNum": 1, "oId": "", "lang": "0"})
    items = data.get("Items", []) if isinstance(data, dict) else []
    results["big_totalrec"] = {"status": status, "n_items": len(items),
                                 "distinct_assets": sorted(set(i.get("AssetName") for i in items))}

    # נסיון 2: pageNum גבוה (אם 30/עמוד, עמוד 50 = פריטים 1470-1500)
    all_assets = set()
    for page in (1, 20, 50, 100, 150, 200, 249):
        status, data = fetch({"qType": 1, "dType": 1, "TotalRec": 1, "pageNum": page, "oId": "", "lang": "0"})
        items = data.get("Items", []) if isinstance(data, dict) else []
        page_assets = sorted(set(i.get("AssetName") for i in items))
        results[f"page_{page}"] = {"status": status, "n_items": len(items), "distinct_assets": page_assets}
        all_assets.update(page_assets)

    txt = json.dumps(results, ensure_ascii=False, indent=2)
    print(txt)
    (OUT / "tase_deriv_filters.json").write_text(txt, encoding="utf-8")
    (OUT / "tase_deriv_all_assets.txt").write_text("\n".join(sorted(a for a in all_assets if a)), encoding="utf-8")


if __name__ == "__main__":
    main()
