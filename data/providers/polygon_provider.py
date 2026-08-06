"""
Polygon.io implementation of the DataProvider interface.
Requires POLYGON_API_KEY in the environment. Uses the free `requests`
library directly (no vendor SDK dependency) via the aggregates endpoint.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import pandas as pd

from data.providers.base import DataProvider, DataProviderError


class PolygonProvider(DataProvider):
    name = "polygon"
    BASE_URL = "https://api.polygon.io"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("POLYGON_API_KEY")
        if not self.api_key:
            raise DataProviderError("POLYGON_API_KEY is not set")

    def get_ohlcv(self, symbol: str, lookback_days: int = 260) -> pd.DataFrame:
        try:
            import requests
        except ImportError as e:
            raise DataProviderError("requests is not installed. Run: pip install requests") from e

        end = date.today()
        # extra calendar-day buffer to guarantee enough trading sessions
        start = end - timedelta(days=int(lookback_days * 1.6) + 10)
        url = (
            f"{self.BASE_URL}/v2/aggs/ticker/{symbol}/range/1/day/"
            f"{start.isoformat()}/{end.isoformat()}"
        )
        params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": self.api_key}

        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            raise DataProviderError(f"Polygon request failed for {symbol}: {e}") from e

        results = payload.get("results")
        if not results:
            raise DataProviderError(f"Polygon returned no data for {symbol}")

        df = pd.DataFrame(results)
        df["date"] = pd.to_datetime(df["t"], unit="ms").dt.date
        df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
        df = df.set_index("date")[["open", "high", "low", "close", "volume"]]
        return df.tail(lookback_days)
