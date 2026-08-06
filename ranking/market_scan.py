from data.providers.market_symbols import get_all_us_symbols
from data.providers.polygon_provider import PolygonProvider
from config import ScanFilters


def scan_market_for_flow():
    provider = PolygonProvider()

    all_symbols = set(get_all_us_symbols())
    snapshot = provider.get_market_snapshot()

    print(f"DEBUG: NASDAQ list count = {len(all_symbols)}")
    print(f"DEBUG: Polygon snapshot count = {len(snapshot)}")
    print(f"DEBUG: sample NASDAQ symbols = {list(all_symbols)[:5]}")
    print(f"DEBUG: sample Polygon symbols = {list(snapshot.keys())[:5]}")

    candidates = [
        symbol for symbol, data in snapshot.items()
        if symbol in all_symbols
        and data["price"] >= ScanFilters.min_price
        and data["day_volume"] >= ScanFilters.min_avg_volume
    ]

    print(f"DEBUG: candidates after price/volume filter = {len(candidates)}")

    qualified = []
    for symbol in candidates:
        market_cap = provider.get_market_cap(symbol)
        if market_cap and market_cap >= ScanFilters.min_market_cap:
            qualified.append(symbol)

    return qualified
