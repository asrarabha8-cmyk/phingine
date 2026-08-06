"""
Provider registry: the single place that knows which providers exist.
To add Finnhub, Financial Modeling Prep, or Alpha Vantage: create
<name>_provider.py implementing DataProvider (copy yfinance_provider.py or
polygon_provider.py as a template — same three parts: read config/API key,
call the vendor endpoint, normalize into the [open, high, low, close, volume]
DataFrame), then add one line to PROVIDERS below. No other file changes.
"""
from __future__ import annotations

from typing import Type

from data.providers.base import DataProvider, DataProviderError
from data.providers.yfinance_provider import YFinanceProvider
from data.providers.polygon_provider import PolygonProvider

PROVIDERS: dict[str, Type[DataProvider]] = {
    "yfinance": YFinanceProvider,
    "polygon": PolygonProvider,
    # "finnhub": FinnhubProvider,
    # "fmp": FinancialModelingPrepProvider,
    # "alpha_vantage": AlphaVantageProvider,
}


def get_provider(name: str, **kwargs) -> DataProvider:
    if name not in PROVIDERS:
        raise ValueError(f"Unknown provider '{name}'. Available: {list(PROVIDERS)}")
    return PROVIDERS[name](**kwargs)


class FallbackProvider(DataProvider):
    """Tries providers in order, falling back on DataProviderError.
    Use this in the pipeline so a single provider outage doesn't stop
    the daily historical update."""

    name = "fallback"

    def __init__(self, providers: list[DataProvider]):
        if not providers:
            raise ValueError("FallbackProvider needs at least one provider")
        self._providers = providers

    def get_ohlcv(self, symbol: str, lookback_days: int = 260):
        last_error = None
        for provider in self._providers:
            try:
                return provider.get_ohlcv(symbol, lookback_days)
            except DataProviderError as e:
                last_error = e
                continue
        raise DataProviderError(
            f"All providers failed for {symbol}. Last error: {last_error}"
        )
