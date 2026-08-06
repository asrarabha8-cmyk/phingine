"""
A fake DataProvider that generates deterministic synthetic OHLCV data.
Used only in tests, so the full pipeline (provider -> indicators -> flow
score -> storage -> alerts -> ranking -> backtest) can be exercised without
any network access or real API keys.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data.providers.base import DataProvider


class SyntheticProvider(DataProvider):
    name = "synthetic"

    def __init__(self, seed: int = 42, trend: str = "accumulation"):
        self._seed = seed
        self._trend = trend

    def get_ohlcv(self, symbol: str, lookback_days: int = 260) -> pd.DataFrame:
        rng = np.random.default_rng(abs(hash(symbol)) % (2**32) + self._seed)
        dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=lookback_days)

        base_price = 10 + rng.uniform(0, 40)
        prices = [base_price]
        volumes = []
        base_volume = rng.uniform(500_000, 3_000_000)

        for i in range(1, lookback_days):
            if self._trend == "accumulation" and i > lookback_days - 15:
                # sideways-to-mild-up price, rising volume (late window)
                drift = rng.normal(0.05, 0.4)
                vol = base_volume * rng.uniform(1.1, 2.2)
            elif self._trend == "distribution" and i > lookback_days - 15:
                drift = rng.normal(-0.6, 0.4)
                vol = base_volume * rng.uniform(1.1, 2.0)
            else:
                drift = rng.normal(0.0, 0.6)
                vol = base_volume * rng.uniform(0.6, 1.4)
            prices.append(max(0.5, prices[-1] * (1 + drift / 100)))
            volumes.append(vol)
        volumes.append(base_volume)  # align length

        closes = np.array(prices)
        highs = closes * (1 + rng.uniform(0.001, 0.02, size=lookback_days))
        lows = closes * (1 - rng.uniform(0.001, 0.02, size=lookback_days))
        opens = closes * (1 + rng.normal(0, 0.005, size=lookback_days))

        df = pd.DataFrame({
            "open": opens, "high": highs, "low": lows,
            "close": closes, "volume": volumes,
        }, index=dates.date)
        df.index.name = "date"
        return df
