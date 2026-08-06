"""
Yahoo Finance implementation of the DataProvider interface.
Free, no API key, but rate-limited and occasionally flaky — wrap failures
into DataProviderError so the pipeline can fall back to another provider.
"""
from __future__ import annotations

import pandas as pd

from data.providers.base import DataProvider, DataProviderError


class YFinanceProvider(DataProvider):
    name = "yfinance"

    def get_ohlcv(self, symbol: str, lookback_days: int = 260) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as e:
            raise DataProviderError(
                "yfinance is not installed. Run: pip install yfinance"
            ) from e

        try:
            period_days = max(lookback_days + 10, 30)  # small buffer for weekends/holidays
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=f"{period_days}d", interval="1d", auto_adjust=True)
        except Exception as e:
            raise DataProviderError(f"yfinance request failed for {symbol}: {e}") from e

        if df is None or df.empty:
            raise DataProviderError(f"yfinance returned no data for {symbol}")

        df = df.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })[["open", "high", "low", "close", "volume"]]
        df.index = df.index.date
        df.index.name = "date"
        return df.tail(lookback_days)
