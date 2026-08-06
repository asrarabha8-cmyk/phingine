# Historical Institutional Flow Engine

نظام كامل لتخزين وتحليل التدفقات المؤسسية عبر الزمن لكل سهم، مبني ليُدمج داخل مشروع
**Phoenix Scanner** الحالي (Streamlit) دون تعارض مع الكود الموجود.

تم اختبار كل جزء من هذا المشروع فعليًا (انظر `run_checks.py` و`tests/`) —
هذا ليس Prototype، الكود جاهز للتشغيل الآن ويحتاج فقط لربطه ببيانات حقيقية.

## البنية (Architecture)

```
phoenix_flow_engine/
├── config.py                  # كل الإعدادات والعتبات (Thresholds) في مكان واحد
├── pipeline.py                 # نقطة التشغيل اليومية: Provider → Indicators → DB → Alerts
├── data/
│   ├── database.py              # طبقة SQLite (Repository Pattern قابل للترحيل إلى Postgres)
│   └── providers/
│       ├── base.py               # الواجهة المجردة (Interface) لأي مزود بيانات
│       ├── yfinance_provider.py
│       ├── polygon_provider.py
│       └── registry.py           # لإضافة أي مزود جديد بسطر واحد
├── analysis/
│   ├── indicators.py             # OBV, CMF, MFI, A/D, VWAP Position, EMA20/50/200
│   ├── flow_score.py             # Institutional Flow Score (0-100)
│   ├── flow_trend.py             # Flow Trend: 5 حالات محسوبة من عدة جلسات
│   └── detection.py              # Early Accumulation / Distribution
├── alerts/
│   ├── alert_engine.py           # Smart Alerts (Surge / Drop)
│   └── explainer.py              # AI Explanation (Template + Claude API اختياري)
├── ranking/
│   └── ranking_engine.py         # ترتيب الأسهم حسب Flow وليس السعر
├── backtesting/
│   └── backtest_engine.py        # Win Rate, Profit Factor, Sharpe, Max Drawdown...
├── ui/
│   └── charts.py                 # مكونات Streamlit جاهزة للدمج في التطبيق الحالي
└── tests/
    ├── synthetic_provider.py     # بيانات اصطناعية لاختبار كامل الـ pipeline بدون إنترنت
    └── test_end_to_end.py        # اختبارات pytest
```

## لماذا SQLite الآن مع سهولة الانتقال لـ PostgreSQL لاحقًا

كل الاستعلامات في `data/database.py` مكتوبة بصياغة SQL قياسية (ANSI)، ولا تُستخدم أي
دالة خاصة بـ SQLite فقط. عند الحاجة للانتقال:

1. أنشئ class جديد `PostgresDatabase` بنفس الدوال العامة الموجودة في `Database`
   (`upsert_flow_record`, `get_history`, `get_latest`, ...).
2. عدّل `get_database()` في نهاية الملف ليُرجع النسخة الجديدة عند
   `settings.db.engine == "postgres"`.
3. لا تحتاج لتعديل أي ملف آخر في المشروع — `analysis/`, `alerts/`, `ranking/`,
   `backtesting/` تتعامل فقط مع واجهة `Database` العامة.

## إضافة مزود بيانات جديد (Finnhub, FMP, Alpha Vantage)

انسخ `polygon_provider.py` كقالب، نفّذ `get_ohlcv()` بحيث يرجع DataFrame بالأعمدة
`[open, high, low, close, volume]` مفهرسة بالتاريخ، ثم أضف سطرًا واحدًا في
`data/providers/registry.py`. لا شيء آخر يحتاج تعديل.

## التشغيل اليومي

```python
from data.providers.yfinance_provider import YFinanceProvider
from pipeline import run_daily_update

symbols = ["AAPL", "SILO", "TSLA"]  # أو القائمة الكاملة من Phoenix Scanner
provider = YFinanceProvider()
result = run_daily_update(symbols, provider)

print(result["updated"], result["failed"])
for alert in result["alerts"]:
    print(alert.symbol, alert.alert_type, alert.explanation)
```

استخدم Polygon (المشترك فيه بالفعل) بدلاً من yfinance عبر:
```python
from data.providers.polygon_provider import PolygonProvider
provider = PolygonProvider()  # يقرأ POLYGON_API_KEY من البيئة
```

أو استخدم `FallbackProvider` من `registry.py` لتجربة أكثر من مزود بالترتيب.

## الدمج في Streamlit

```python
from data.database import get_database
from ui.charts import render_symbol_history_page, render_ranking_page, render_backtest_page

db = get_database()

page = st.sidebar.radio("Page", ["Symbol History", "Ranking", "Backtest"])
if page == "Symbol History":
    symbol = st.text_input("Symbol", "AAPL")
    render_symbol_history_page(db, symbol)
elif page == "Ranking":
    render_ranking_page(db)
else:
    render_backtest_page(db)
```

## AI Explanation

كل Alert يحصل تلقائيًا على تفسير مبني على الأرقام الفعلية (Template مضمون يعمل دائمًا).
إذا ضبطت متغير البيئة `ANTHROPIC_API_KEY`، سيُعاد صياغة نفس التفسير بأسلوب أكثر
طبيعية عبر Claude API، مع إبقاء كل رقم كما هو (لا يُسمح للنموذج باختراع أرقام).

## التشغيل والاختبار

```bash
pip install -r requirements.txt
python3 run_checks.py          # اختبار شامل بدون إنترنت (بيانات اصطناعية)
# أو
pytest tests/ -v               # نفس الاختبارات عبر pytest
```

جميع الاختبارات الستة تعمل الآن بنجاح (تم التحقق فعليًا أثناء بناء المشروع).

## حدود متعمّدة (Scope Boundaries) — للشفافية لا للتقصير

- الـ Backtest حاليًا يحاكي صفقة واحدة في كل مرة لكل سهم (لا محاكاة محفظة كاملة
  بتوزيع رأس مال أو صفقات متزامنة). هذا امتداد منفصل ومنطقي لاحقًا وليس نقصًا في المنطق الحالي.
- `vwap_position` يُحسب كـ VWAP متدحرج (Rolling) من بيانات يومية لأن معظم المزودين
  المجانيين لا يوفرون بيانات داخل اليوم (Intraday) مجانًا؛ عند توفر بيانات دقيقة،
  استبدلها بـ VWAP حقيقي للجلسة في `analysis/indicators.py` فقط.
