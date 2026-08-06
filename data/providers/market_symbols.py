import requests
import pandas as pd
from io import StringIO

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"


def get_all_us_symbols():
    """
    يجيب كل رموز NASDAQ, NYSE, AMEX من مصدر NASDAQ المجاني.
    يستبعد تلقائيًا: ETFs, Test Issues, ورموز فيها رموز خاصة (warrants, units...).
    """
    symbols = set()

    # NASDAQ listed
    resp = requests.get(NASDAQ_LISTED_URL, timeout=15)
    df = pd.read_csv(StringIO(resp.text), sep="|")
    df = df[df["Test Issue"] == "N"]
    df = df[df["ETF"] == "N"]
    symbols.update(df["Symbol"].dropna().tolist())

    # NYSE + AMEX (other listed)
    resp2 = requests.get(OTHER_LISTED_URL, timeout=15)
    df2 = pd.read_csv(StringIO(resp2.text), sep="|")
    df2 = df2[df2["Test Issue"] == "N"]
    df2 = df2[df2["ETF"] == "N"]
    symbols.update(df2["ACT Symbol"].dropna().tolist())

    # تنظيف: استبعاد رموز فيها نقطة أو دولار (warrants, preferred shares...)
    clean_symbols = [
        s for s in symbols
        if isinstance(s, str) and s.isalpha() and len(s) <= 5
    ]

    return sorted(clean_symbols)
