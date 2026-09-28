"""ממשיך את הבדיקה: dType/qType כנראה מסננים (למשל מדד מול מניה בודדת) -
הבקשה הראשונה עם dType=1 החזירה רק אופציות מדד ת"א-35. מנסה dType אחרים
ו-pageNum כדי למצוא את המניות הבודדות (כולל בזן/ברס/פנק/פרן שחסרים
ב-option_ticker_parse.py).

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
    summary = {}
    all_items = []
    # dType 1-6, qType 1-2, כמה pageNum לכל אחד
    for dtype in range(1, 7):
        for qtype in (1, 2):
            status, data = fetch({"qType": qtype, "dType": dtype, "TotalRec": 1,
                                    "pageNum": 1, "oId": "", "lang": "0"})
            if status != 200 or not isinstance(data, dict):
                summary[f"d{dtype}q{qtype}"] = {"status": status}
                continue
            items = data.get("Items", [])
            assets = sorted(set(i.get("AssetName") for i in items))
            summary[f"d{dtype}q{qtype}"] = {
                "status": status, "TotalRec": data.get("TotalRec"),
                "n_items": len(items), "distinct_assets": assets[:15],
            }
            all_items.extend(items)

    txt = json.dumps(summary, ensure_ascii=False, indent=2)
    print(txt)
    (OUT / "tase_deriv_filters.json").write_text(txt, encoding="utf-8")

    all_assets = sorted(set(i.get("AssetName") for i in all_items if i.get("AssetName")))
    print(f"\n{len(all_assets)} distinct AssetName across all filter combos tried:")
    for a in all_assets:
        print(" ", a)
    (OUT / "tase_deriv_all_assets.txt").write_text("\n".join(all_assets), encoding="utf-8")


if __name__ == "__main__":
    main()
