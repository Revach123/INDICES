"""נסיון API-export רשמי (מסופק ע"י המשתמש) - עשוי להחזיר את כל ~7500
הנגזרים כ-CSV בבקשה אחת, במקום 260 בקשות מדוגמות (probe_tase_derivatives.py).

הרצה: python scripts/probe_tase_export.py
"""
from pathlib import Path

import requests

URL = "https://api.tase.co.il/api/export/derivativesall"
HEADERS = {
    "accept": "text/csv",
    "accept-language": "he-IL",
    "content-type": "application/json;charset=UTF-8",
    "referer": "https://market.tase.co.il/",
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"),
    "origin": "https://market.tase.co.il",
}
BODY = {"FilterData": {"qType": 6, "dType": "1", "TotalRec": 1, "pageNum": 1,
                        "oId": "", "lang": "0", "isNext": False}, "isAdd": True}
OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)


def main():
    r = requests.post(URL, headers=HEADERS, json=BODY, timeout=60)
    print("status:", r.status_code)
    print("content-type:", r.headers.get("content-type"))
    print("content-length:", len(r.content))
    print("first 2000 chars:")
    print(r.text[:2000])
    (OUT / "tase_export.csv").write_bytes(r.content)


if __name__ == "__main__":
    main()
