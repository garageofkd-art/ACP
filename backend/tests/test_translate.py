"""English -> StrategySpec translation (deterministic fallback path).

The Claude path needs a network + API key, so these tests exercise the offline
parser that the product falls back to. They lock in that everyday phrasings map
to the right bounded primitives.
"""
from app.config import Settings
from app.research.translate import (
    english_to_spec,
    explain_result,
    fallback_parse,
)


def _no_key():
    return Settings(anthropic_api_key="")


def test_breakout_phrasing_maps_to_ndayhigh_and_ndaylow():
    spec = fallback_parse(
        "Buy when the close breaks above the 20-day high, "
        "exit when the close falls below the 10-day low.")
    assert len(spec.entry) == 1 and len(spec.exit) == 1
    e = spec.entry[0]
    assert e.indicator == "close" and e.op == ">"
    assert e.other_indicator == "ndayhigh" and e.other_lookback == 20
    x = spec.exit[0]
    assert x.indicator == "close" and x.op == "<"
    assert x.other_indicator == "ndaylow" and x.other_lookback == 10


def test_rsi_thresholds_and_stop_loss():
    spec = fallback_parse(
        "Buy when RSI(5) is below 35, sell when RSI(5) rises above 55, 5% stop loss.")
    assert spec.entry[0].indicator == "rsi" and spec.entry[0].lookback == 5
    assert spec.entry[0].op == "<" and spec.entry[0].value == 35
    assert spec.exit[0].op == ">" and spec.exit[0].value == 55
    assert spec.stop_pct == 0.05


def test_moving_average_phrasing_maps_to_sma():
    spec = fallback_parse(
        "Go long when price is above the 50-day moving average; "
        "exit when price drops below the 20-day moving average.")
    assert spec.entry[0].other_indicator == "sma" and spec.entry[0].other_lookback == 50
    assert spec.entry[0].op == ">"
    assert spec.exit[0].other_indicator == "sma" and spec.exit[0].other_lookback == 20
    assert spec.exit[0].op == "<"


def test_english_to_spec_uses_fallback_without_api_key():
    spec = english_to_spec(
        "Buy when close breaks above the 20-day high", settings=_no_key())
    assert spec.entry and spec.entry[0].other_indicator == "ndayhigh"


def test_explain_result_is_honest_about_no_edge():
    spec = english_to_spec("Buy when close breaks above the 20-day high", settings=_no_key())
    result = {
        "name": spec.name, "timeframe": "day",
        "full": {"net_pnl": -5000, "num_trades": 40},
        "test": {"net_pnl": -3000, "num_trades": 25, "profit_factor": 0.8, "expectancy": -120},
        "verdict": "NO EDGE",
    }
    text = explain_result(spec, result, settings=_no_key())
    assert "NO EDGE" in text
    assert "edge doesn't survive" in text


def test_explain_result_insufficient_data():
    spec = english_to_spec("Buy when RSI(5) is below 30", settings=_no_key())
    result = {
        "name": spec.name, "timeframe": "day",
        "full": {"net_pnl": 100, "num_trades": 5},
        "test": {"net_pnl": 50, "num_trades": 3, "profit_factor": 1.1, "expectancy": 10},
        "verdict": "INSUFFICIENT DATA",
    }
    text = explain_result(spec, result, settings=_no_key())
    assert "INSUFFICIENT DATA" in text and "too few" in text
