from data.providers.market_symbols import get_all_us_symbols
from data.providers.polygon_provider import PolygonProvider
from analysis.flow_score import calculate_flow_score
from config import ScanFilters


def scan_market_for_flow():
    provider = PolygonProvider()
    all_symbols = get_all_us_symbols()

    qualified = []
    for symbol in all_symbols:
        try:
            snapshot = provider.get_snapshot(symbol)  # سعر + حجم + قيمة سوقية
            if (
                snapshot["price"] >= ScanFilters.min_price
                and snapshot["avg_volume"] >= ScanFilters.min_avg_volume
                and snapshot["market_cap"] >= ScanFilters.min_market_cap
            ):
                qualified.append(symbol)
        except Exception:
            continue

    return qualified
