from concurrent.futures import ThreadPoolExecutor, as_completed

from data.providers.market_symbols import get_all_us_symbols
from data.providers.polygon_provider import PolygonProvider
from config import ScanFilters


def scan_market_for_flow():
    provider = PolygonProvider()

    all_symbols = set(get_all_us_symbols())
    snapshot = provider.get_market_snapshot()

    candidates = [
        symbol for symbol, data in snapshot.items()
        if symbol in all_symbols
        and data["price"] >= ScanFilters.min_price
        and data["day_volume"] >= ScanFilters.min_avg_volume
    ]

    qualified = []
    with ThreadPoolExecutor(max_workers=35) as executor:
        futures = {executor.submit(provider.get_market_cap, sym): sym for sym in candidates}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                market_cap = future.result()
                if market_cap and market_cap >= ScanFilters.min_market_cap:
                    qualified.append(symbol)
            except Exception:
                continue

    return qualified
