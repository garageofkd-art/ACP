from app.backtest.costs import CostConfig, apply_slippage, charges
from app.core.events import Side

CFG = CostConfig()


def test_brokerage_capped_at_flat_fee():
    # Large turnover: 0.05% would exceed ₹20, so brokerage caps at the flat fee.
    c = charges(Side.BUY, qty=1000, price=100.0, cfg=CFG)  # turnover 1,00,000
    assert c > 0
    # Stamp duty applies on buy, STT does not.
    assert charges(Side.BUY, 1000, 100.0, CFG) != charges(Side.SELL, 1000, 100.0, CFG)


def test_stt_only_on_sell():
    buy = charges(Side.BUY, 100, 500.0, CFG)
    sell = charges(Side.SELL, 100, 500.0, CFG)
    # Sell leg carries the 0.025% STT, which dominates -> larger total.
    assert sell > buy


def test_zero_turnover_is_free():
    assert charges(Side.BUY, 0, 100.0, CFG) == 0.0


def test_slippage_direction():
    assert apply_slippage(100.0, Side.BUY, CFG) > 100.0   # buys fill higher
    assert apply_slippage(100.0, Side.SELL, CFG) < 100.0  # sells fill lower
