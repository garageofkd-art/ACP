"""NSE intraday-equity (MIS) cost model.

Centralized so backtest and paper trading apply identical, realistic charges —
results aren't fantasy. Rates are configurable and should be verified against
Upstox's current schedule; defaults reflect typical 2024-25 intraday equity
charges.

Charge components (intraday equity):
  - brokerage:      min(flat per order, % of turnover)  [Upstox: ~₹20 or 0.05%]
  - STT:            0.025% on the SELL leg only
  - exchange txn:   ~0.00297% of turnover (NSE)
  - SEBI turnover:  ₹10 per crore (0.0001%)
  - GST:            18% on (brokerage + exchange txn + SEBI)
  - stamp duty:     0.003% on the BUY leg only
  - slippage:       modelled separately (applied to fill price)
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.events import Side


@dataclass(frozen=True, slots=True)
class CostConfig:
    brokerage_per_order: float = 20.0
    brokerage_pct: float = 0.0005      # 0.05%
    stt_buy_pct: float = 0.0           # intraday: no STT on buy
    stt_sell_pct: float = 0.00025      # 0.025% (sell side)
    exchange_txn_pct: float = 0.0000297  # ~0.00297%
    sebi_pct: float = 0.000001         # ₹10 / crore
    gst_pct: float = 0.18
    stamp_buy_pct: float = 0.00003     # 0.003% (buy side)
    slippage_pct: float = 0.0002       # 0.02% adverse fill


# Delivery/positional charges: STT is 0.1% on BOTH legs, higher stamp duty, but
# spread across far bigger moves than intraday — so cost as a % of the move is small.
DELIVERY_COSTS = CostConfig(
    brokerage_per_order=20.0,
    brokerage_pct=0.0025,
    stt_buy_pct=0.001,
    stt_sell_pct=0.001,
    exchange_txn_pct=0.0000297,
    sebi_pct=0.000001,
    gst_pct=0.18,
    stamp_buy_pct=0.00015,   # 0.015% (delivery)
    slippage_pct=0.0005,
)


def charges(side: Side, qty: int, price: float, cfg: CostConfig) -> float:
    """Total statutory + brokerage charges for one executed leg."""
    turnover = qty * price
    if turnover <= 0:
        return 0.0
    brokerage = min(cfg.brokerage_per_order, turnover * cfg.brokerage_pct)
    stt = turnover * (cfg.stt_sell_pct if side == Side.SELL else cfg.stt_buy_pct)
    exch = turnover * cfg.exchange_txn_pct
    sebi = turnover * cfg.sebi_pct
    gst = cfg.gst_pct * (brokerage + exch + sebi)
    stamp = turnover * cfg.stamp_buy_pct if side == Side.BUY else 0.0
    return brokerage + stt + exch + sebi + gst + stamp


def apply_slippage(price: float, side: Side, cfg: CostConfig) -> float:
    """Adverse-fill model: buys fill a touch higher, sells a touch lower."""
    if side == Side.BUY:
        return price * (1 + cfg.slippage_pct)
    return price * (1 - cfg.slippage_pct)
