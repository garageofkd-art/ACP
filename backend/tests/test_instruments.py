"""Offline-safe sanity checks for the trading universe."""
from app.data.instruments import UNIVERSE, UNIVERSE_BY_SYMBOL


def test_user_picks_present():
    symbols = {i.symbol for i in UNIVERSE}
    # "HDFC" maps to HDFCBANK post-merger.
    assert {"HDFCBANK", "TCS", "MRF"} <= symbols


def test_mrf_is_low_priority():
    assert UNIVERSE_BY_SYMBOL["MRF"].low_priority is True


def test_isin_fallback_keys_well_formed():
    for inst in UNIVERSE:
        assert inst.isin_fallback.startswith("INE")
        assert len(inst.isin_fallback) == 12
