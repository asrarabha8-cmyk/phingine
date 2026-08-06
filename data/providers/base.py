"""
Data Provider Interface.

Any market-data source (Yahoo Finance, Finnhub, Polygon, Financial Modeling
Prep, Alpha Vantage, ...) implements this ABC. The rest of the system
(pipeline.py, analysis/, alerts/, ranking/, backtesting/) only ever talks to
this interface — never to a specific vendor's SDK. To add a new provider:

    1. Create data/providers/<name>_provider.py
    2. Subclass DataProvider and implement get_ohlcv()
    3. Register it in data/providers/registry.py

Nothing else in the project changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional
import pandas as pd


@dataclass(frozen=True)
class OHLCVBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class DataProviderError(Exception):
    """Raised for any provider-side failure (network, auth, rate limit, bad symbol)."""


class DataProvider(ABC):
    """Contract every market-data provider must satisfy."""

    name: str = "base"

    @abstractmethod
    def get_ohlcv(self, symbol: str, lookback_days: int = 260) -> pd.DataFrame:
        """
        Return a DataFrame indexed by date (ascending) with columns:
        ['open', 'high', 'low', 'close', 'volume'].
        Must raise DataProviderError on failure rather than returning
        an empty/partial frame silently, so the pipeline can distinguish
        "no data" from "provider is broken".
        """
        raise NotImplementedError

    def supports_symbol(self, symbol: str) -> bool:
        """Optional override — default assumes all US equity tickers are supported."""
        return True
