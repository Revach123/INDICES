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

## כלל קריטי לשימוש ב-swap_ticker_map.csv: ETF אינו תחליף חוקי למדד

`index_id` שממופה מטיקר סוואפ (`swap_ticker_map.csv`) חייב להיות טיקר
**ברמת מדד** (Yahoo `instrumentType == "INDEX"`) - **לא** מחיר ETF, גם אם
ה-ETF "מצטבר" (Accumulating, עוקב TR נאמנה). הסיבה: הצרכן היחיד של הנתון
הזה (MASLULIM `swap_index_pricing.py`) מציב אותו ישירות בנוסחה
`יחידות × שער` שמניחה שה"שער" באותו קנה-מידה בדיוק כמו "שער נכס הבסיס
במועד ההתקשרות בעסקה" שהדוח המקורי דיווח - כלומר רמת המדד עצמו (לדוגמה
Nasdaq-100 ~25,000 נקודות). מחיר יחידת ETF (לדוגמה CNDX.L ~1,755$) הוא
בקנה-מידה שרירותי לגמרי שנקבע ע"י מבנה הקרן, לא פרופורציונלי לרמת המדד -
הצבתו בנוסחה מייצרת חשיפה שגויה בסדרי גודל, בלי שתקרת הסבירות (LEVERAGE_CAP
בקוד ה-MASLULIM) בהכרח תופסת את זה (נבדק בפועל: MAE **הורע** אחרי מעבר
ל-CNDX.L/C50.PA, למרות שאלו כן עוקבי-TR אמיתיים).

לעומת זאת `^RUTTR` (Russell 2000 Total Return) תקין להצבה ישירה - זה
טיקר INDEX אמיתי, באותה משפחת מדדים ואותו קנה-מידה כמו `^RUT` (מדד המחיר),
רק עם בסיס-חישוב שונה (TR מצטבר מאז תאריך ההשקה, לא מייצג "מחיר יחידה").

**מסקנה מעשית**: כשאין טיקר TR ברמת מדד (INDEX) זמין, עדיף להישאר על מדד
המחיר (Price, לא TR) - עדיף קנה-מידה נכון עם פער TR קטן-יחסית, על פני
קנה-מידה שגוי לגמרי. זו הסיבה ש-`nasdaq100`/`stoxx50` ב-`swap_ticker_map.csv`
חזרו למדדי המחיר (^NDX/^STOXX50E) אחרי שנבדק בפועל שה-ETF-ים מזיקים.

## הרצה

```
pip install requests pandas lxml
python scripts/fetch_prices.py
python scripts/fetch_constituents.py
```

ב-CI: `.github/workflows/fetch.yml` - `workflow_dispatch` + cron יומי
(04:30 UTC), מריץ את שני הסקריפטים ומבצע commit לתוצאות.
