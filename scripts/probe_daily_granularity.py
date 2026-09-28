"""המשך בדיקת הגרנולריות: אולי events=history (לא רק range) הוא שגורם
לקוארסינג, לא ה-period עצמו. משווה את כל הצירופים.
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

PERIOD1 = 1704067200  # 2024-01-01 UTC
PERIOD2 = int(time.time())


def check(symbol, params, label):
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    r = session.get(CHART_URL.format(symbol=symbol), params=params, timeout=30)
    data = r.json()
    result = (data.get("chart") or {}).get("result")
    if not result:
        return {"label": label, "params": params, "error": (data.get("chart") or {}).get("error")}
    ts = result[0].get("timestamp") or []
    if len(ts) < 3:
        return {"label": label, "params": params, "n": len(ts)}
    gaps = [(ts[i] - ts[i-1]) / 86400 for i in range(1, min(len(ts), 15))]
    return {"label": label, "params": params, "n": len(ts), "gaps": [round(g, 1) for g in gaps]}


def main():
    report = {}
    report["period_no_events"] = check("AAPL", {"period1": PERIOD1, "period2": PERIOD2, "interval": "1d"}, "period, no events")
    report["period_with_events"] = check("AAPL", {"period1": PERIOD1, "period2": PERIOD2, "interval": "1d", "events": "history"}, "period + events=history")
    report["period_with_events_div"] = check("AAPL", {"period1": PERIOD1, "period2": PERIOD2, "interval": "1d", "events": "div,splits"}, "period + events=div,splits")
    txt = json.dumps(report, ensure_ascii=False, indent=2)
    print(txt)
    (OUT / "daily_granularity.json").write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
