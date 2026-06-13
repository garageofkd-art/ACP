"""Universe selection: nifty50 (default) vs the broad mid/small-cap research set."""
from app.config import Settings
from app.data.instruments import active_symbols


def test_broad_universe_is_larger():
    n50 = active_symbols(Settings(universe="nifty50"))
    broad = active_symbols(Settings(universe="broad"))
    assert len(n50) >= 50
    assert len(broad) > len(n50) + 50          # meaningfully bigger
    assert set(n50) <= set(broad)              # broad is a superset


def test_default_universe_is_nifty50():
    assert len(active_symbols(Settings())) == len(active_symbols(Settings(universe="nifty50")))
