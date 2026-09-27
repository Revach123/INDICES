# INDICES

נתוני מדדים (מחירים היסטוריים/יומיים + הרכבים) למדדי המניות/סחורות/מט"ח
המובילים בעולם ובישראל - נבנה כדי לתמוך בחישוב חשיפה אמיתית (נכון לתאריך
הדוח, לא לפי תאריך פתיחת עסקה) בעסקאות סוואפ בפרויקט MASLULIM.

## מבנה

- `data/universe.csv` - רשימת המדדים: מזהה פנימי, טיקר Yahoo Finance, שמות
  בעברית/אנגלית, אזור, סוג נכס, וקישור ויקיפדיה (להרכב, אם קיים).
- `data/prices/<index_id>.csv` - היסטוריית OHLC יומית מלאה (`date,open,high,low,close,volume`).
- `data/constituents/<index_id>.csv` - טבלת הרכב המדד (רק למדדים עם `wikipedia_url`).

## מקורות נתונים

נבדקה נגישות ממש (`scripts/probe.py`) מ-GitHub Actions, כי ה-sandbox של
הסשן חוסם כמעט כל תעבורה יוצאת חוץ מ-GitHub/npm/pypi:

| מקור | סטטוס | שימוש |
|---|---|---|
| Yahoo Finance chart API | ✅ עובד | מחירים (`fetch_prices.py`) |
| Wikipedia | ✅ עובד | הרכבי מדדים (`fetch_constituents.py`) |
| Stooq, Investing.com, TASE | ❌ חסום (הגנת בוט/403) | - |
| SEC.gov | ❌ 403 (דורש User-Agent עם אימייל תקני) | - |
| FRED, ECB | ❌ timeout/DNS | - |
| iShares CSV holdings | ⚠️ URL שגוי בבדיקה, לא נבדק שוב | - |

## מגבלות ידועות

- אין הרכב זמין למדדים סינתטיים של בנקים שנמצאו בדוחות סוואפ של MASLULIM
  (כמו GSC1000N, JPMTVEUI, NDEUCHF) - אין מקור ציבורי חינמי להם.
- `ta_banks` (TA-BANKS5.TA) לא נמצא ב-Yahoo Finance תחת הטיקר הזה - טרם
  נמצא טיקר חלופי נכון.
- MSCI World/EM/ACWI מיוצגים דרך ETF פרוקסי (URTH/EEM/ACWI), לא המדד
  הרשמי של MSCI עצמו (אין מקור חינמי ישיר לנתוני MSCI).
- TOPIX מיוצג דרך ETF פרוקסי (1306.T, Nomura), לא המדד הגולמי (הטיקר
  הישיר `^TPX` לא זמין ב-Yahoo).

## הרצה

```
pip install requests pandas lxml
python scripts/fetch_prices.py
python scripts/fetch_constituents.py
```

ב-CI: `.github/workflows/fetch.yml` - `workflow_dispatch` + cron יומי
(04:30 UTC), מריץ את שני הסקריפטים ומבצע commit לתוצאות.
