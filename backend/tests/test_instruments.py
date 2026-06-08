"""Offline-safe sanity checks for the trading universe."""
from app.data.instruments import UNIVERSE, UNIVERSE_BY_SYMBOL


def test_user_picks_present():
    symbols = {i.symbol for i in UNIVERSE}
    # "HDFC" maps to HDFCBANK post-merger.
    assert {"HDFCBANK", "TCS", "MRF"} <= symbols


def test_mrf_is_low_priority():
    assert UNIVERSE_BY_SYMBOL["MRF"].low_priority is True


def test_isin_fallback_keys_well_formed():
    # ISIN fallback is optional (resolved from the Upstox master at runtime);
    # when present it must be a valid 12-char INE code.
    for inst in UNIVERSE:
        if inst.isin_fallback:
            assert inst.isin_fallback.startswith("INE")
            assert len(inst.isin_fallback) == 12


def test_universe_is_nifty50_plus_mrf():
    assert len(UNIVERSE) == 51  # Nifty 50 + MRF
