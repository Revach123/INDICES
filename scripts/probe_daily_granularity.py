"""בדיקה: האם Yahoo chart API מחזיר גרנולריות יומית אמיתית על פני טווח ארוך
(כמעט 3 שנים) אם משתמשים ב-period1/period2 מפורשים במקום range=max - נמצא
בפועל (9.28.2026) ש-range=max מחזיר נתונים חודשיים/רבעוניים בפועל (לא
יומיים כפי ש-interval=1d ביקש) לטווחים ארוכים, מה שפוגע בחישובי תנודתיות
ריאליזד ובדיוק תמחור-לפי-תאריך-דוח (גם להיסטוריה של מדדים ב-fetch_prices.py
הקיים - לא רק לטיקרים הבודדים החדשים).

הרצה: python scripts/probe_daily_granularity.py
"""
import json
import time
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)

# 2024-01-01 -> now, אותו טווח בדיוק שצריך לארכיון MASLULIM
PERIOD1 = 1704067200  # 2024-01-01 UTC
PERIOD2 = int(time.time())


def check(symbol, params, label):
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    r = session.get(CHART_URL.format(symbol=symbol), params=params, timeout=30)
    data = r.json()
    result = (data.get("chart") or {}).get("result")
    if not result:
        return {"label": label, "error": (data.get("chart") or {}).get("error")}
    ts = result[0].get("timestamp") or []
    if len(ts) < 3:
        return {"label": label, "n": len(ts)}
    gaps = [(ts[i] - ts[i-1]) / 86400 for i in range(1, min(len(ts), 30))]
    return {"label": label, "n": len(ts), "first_gaps_days": [round(g, 1) for g in gaps[:10]]}


def main():
    report = {}
    report["range_max"] = check("AAPL", {"range": "max", "interval": "1d"}, "range=max")
    report["range_2y"] = check("AAPL", {"range": "2y", "interval": "1d"}, "range=2y")
    report["explicit_period"] = check("AAPL", {"period1": PERIOD1, "period2": PERIOD2, "interval": "1d"}, "period1/2 explicit")
    txt = json.dumps(report, ensure_ascii=False, indent=2)
    print(txt)
    (OUT / "daily_granularity.json").write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
