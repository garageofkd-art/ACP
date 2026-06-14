"""Plain English -> StrategySpec (the AI layer of the honest backtester).

A user types their idea in everyday language ("buy when the close breaks the
prior 20-day high, exit below the 10-day low, 5% stop"). `english_to_spec`
turns that into a bounded, runnable `StrategySpec`.

Two paths, same output:

1. **Claude** (when `ANTHROPIC_API_KEY` is set) — translates free-form English
   into the spec schema with structured output. Best coverage of odd phrasings.
2. **Deterministic fallback** — a keyword/regex parser that needs no network and
   no API key, so the product is testable offline and degrades gracefully.

`explain_result` turns a backtest verdict into a short, honest paragraph — again
Claude if available, otherwise a plain template. The honesty is in the numbers,
not the prose: we never dress up a NO EDGE result.
"""
from __future__ import annotations

import re
from typing import Optional

from app.config import Settings, get_settings
from app.strategies.spec import Condition, StrategySpec

# Kept in chat/docs only; not embedded here as a marketing name.
_MODEL = "claude-opus-4-8"

_SYSTEM = """You translate a retail trader's plain-English strategy into a strict JSON spec.

Allowed indicators ONLY: close, sma, ndayhigh, ndaylow, rsi.
  - close: the day's closing price (lookback 0)
  - sma: simple moving average; lookback = window in days
  - ndayhigh: the highest high of the PRIOR N days; lookback = N (a breakout level)
  - ndaylow: the lowest low of the PRIOR N days; lookback = N
  - rsi: Relative Strength Index; lookback = period (default 14)
Allowed ops ONLY: > < >= <=
A condition compares an indicator to EITHER a numeric `value` OR another indicator
(`other_indicator` + `other_lookback`). Entry fires when ALL entry conditions are
true; exit fires when ANY exit condition is true. Use stop_pct (a fraction like
0.05 for a 5% stop) only if the user mentions a stop loss. timeframe is "day".
Map "moving average"/"MA" to sma, "N-day high"/"breakout" to ndayhigh, etc.
If the idea cannot be expressed with these primitives, get as close as you can."""


# --- Deterministic fallback parser -------------------------------------------------

# Indicator phrase patterns, highest priority first. group(1) (if present) = lookback.
_IND_PATTERNS = [
    ("rsi", re.compile(r"\brsi\s*\(?\s*(\d+)\s*\)?", re.I)),
    ("rsi", re.compile(r"\b(\d+)[\s-]day\s+rsi\b", re.I)),
    ("rsi", re.compile(r"\brsi\b", re.I)),
    ("sma", re.compile(r"\bsma\s*\(?\s*(\d+)\s*\)?", re.I)),
    ("sma", re.compile(r"\b(\d+)[\s-]day\s+(?:simple\s+)?(?:moving average|moving avg|sma|ma)\b", re.I)),
    ("ndayhigh", re.compile(r"\b(\d+)[\s-]day\s+high\b", re.I)),
    ("ndaylow", re.compile(r"\b(\d+)[\s-]day\s+low\b", re.I)),
    ("close", re.compile(r"\b(?:closing price|close|price)\b", re.I)),
]
_DEFAULT_LB = {"rsi": 14, "sma": 20, "ndayhigh": 20, "ndaylow": 20, "close": 0}

_GT = re.compile(r"\b(above|over|breaks?(?:\s+above)?|cross(?:es|ing)?\s+above|rises?\s+above|"
                 r"greater(?:\s+than)?|exceeds?|more\s+than|higher(?:\s+than)?)\b", re.I)
_LT = re.compile(r"\b(below|under|breaks?\s+below|cross(?:es|ing)?\s+below|drops?\s+below|"
                 r"falls?\s+below|less(?:\s+than)?|lower(?:\s+than)?|beneath)\b", re.I)

_CLAUSE_RE = re.compile(
    r"\b(buy|enter(?:\s+long)?|go\s+long|long|exit|sell|take\s+profit|"
    r"close\s+(?:the\s+)?position|square\s+off)\b", re.I)
_EXIT_KW = {"exit", "sell", "take profit", "close position", "close the position", "square off"}

_STOP_RE = re.compile(r"(?:stop(?:\s*-?\s*loss)?(?:\s+of)?\s*)?(\d+(?:\.\d+)?)\s*%\s*stop"
                      r"|stop(?:\s*-?\s*loss)?(?:\s+of)?\s*(\d+(?:\.\d+)?)\s*%", re.I)


def _scan_indicators(clause: str):
    """Return [(pos, indicator, lookback)] and the claimed char spans, non-overlapping."""
    claimed: list[tuple[int, int]] = []
    found: list[tuple[int, str, int]] = []

    def overlaps(s: int, e: int) -> bool:
        return any(not (e <= cs or s >= ce) for cs, ce in claimed)

    for ind, pat in _IND_PATTERNS:
        for m in pat.finditer(clause):
            if overlaps(m.start(), m.end()):
                continue
            claimed.append((m.start(), m.end()))
            lb = int(m.group(1)) if (pat.groups and m.group(1)) else _DEFAULT_LB[ind]
            found.append((m.start(), ind, lb))
    found.sort()
    return found, claimed


def _value_in(clause: str, claimed: list[tuple[int, int]]) -> Optional[float]:
    masked = list(clause)
    for s, e in claimed:
        for i in range(s, e):
            masked[i] = " "
    m = re.search(r"(?<![\w.])(\d+(?:\.\d+)?)", "".join(masked))
    return float(m.group(1)) if m else None


def _op_in(clause: str) -> Optional[str]:
    gt = _GT.search(clause)
    lt = _LT.search(clause)
    if gt and (not lt or gt.start() < lt.start()):
        return ">"
    if lt:
        return "<"
    return None


def _parse_condition(clause: str) -> Optional[Condition]:
    inds, claimed = _scan_indicators(clause)
    if not inds:
        return None
    op = _op_in(clause)
    lhs = inds[0]
    if len(inds) >= 2:
        rhs = inds[1]
        return Condition(indicator=lhs[1], lookback=lhs[2], op=op or ">",
                         other_indicator=rhs[1], other_lookback=rhs[2])
    value = _value_in(clause, claimed)
    if value is None or op is None:
        return None
    return Condition(indicator=lhs[1], lookback=lhs[2], op=op, value=value)


def _stop_in(text: str) -> Optional[float]:
    m = _STOP_RE.search(text)
    if not m:
        return None
    pct = m.group(1) or m.group(2)
    return round(float(pct) / 100.0, 6) if pct else None


def _name_from(text: str) -> str:
    words = re.sub(r"\s+", " ", text.strip()).split(" ")
    short = " ".join(words[:6])
    return (short[:48] or "Custom strategy")


def fallback_parse(text: str) -> StrategySpec:
    """Offline, deterministic English -> spec. Best-effort; bounded to our primitives."""
    entry: list[Condition] = []
    exit_: list[Condition] = []

    matches = list(_CLAUSE_RE.finditer(text))
    if matches:
        segments = []
        for i, m in enumerate(matches):
            kw = re.sub(r"\s+", " ", m.group(1).lower())
            label = "exit" if kw in _EXIT_KW else "entry"
            start, end = m.end(), (matches[i + 1].start() if i + 1 < len(matches) else len(text))
            segments.append((label, text[start:end]))
    else:
        segments = [("entry", text)]

    for label, seg in segments:
        cond = _parse_condition(seg)
        if cond is None:
            continue
        (exit_ if label == "exit" else entry).append(cond)

    return StrategySpec(name=_name_from(text), entry=entry, exit=exit_, stop_pct=_stop_in(text))


# --- Claude path -------------------------------------------------------------------

def _llm_parse(text: str, settings: Settings) -> StrategySpec:
    import anthropic  # imported lazily so the package is optional offline

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.parse(
        model=_MODEL,
        max_tokens=2048,
        thinking={"type": "adaptive"},
        system=_SYSTEM,
        messages=[{"role": "user", "content": text}],
        output_format=StrategySpec,
    )
    return response.parsed_output


def english_to_spec(text: str, settings: Settings | None = None, use_llm: bool = True) -> StrategySpec:
    """Translate a plain-English strategy into a runnable StrategySpec.

    Uses Claude when an API key is configured; otherwise (or on any LLM error)
    falls back to the deterministic parser so the product always returns a spec.
    """
    settings = settings or get_settings()
    if use_llm and settings.anthropic_api_key:
        try:
            spec = _llm_parse(text, settings)
            if spec.entry:           # trust the LLM only if it produced a usable entry
                return spec
        except Exception:            # noqa: BLE001 - degrade gracefully, never hard-fail
            pass
    return fallback_parse(text)


# --- Explain the verdict -----------------------------------------------------------

def _template_explanation(spec: StrategySpec, result: dict) -> str:
    v = result["verdict"]
    test = result.get("test") or {}
    full = result.get("full") or {}
    tf = "positional (daily)" if result.get("timeframe") == "day" else "intraday"
    lines = [f'"{spec.name}" — {tf}. Verdict: {v}.']

    if v == "INSUFFICIENT DATA":
        n = test.get("num_trades", 0)
        lines.append(f"Only {n} trades in the out-of-sample period — too few to trust. "
                     "Test on a longer history or a broader universe before drawing conclusions.")
    elif v == "NO EDGE":
        lines.append(
            f"Out-of-sample it made ₹{test.get('net_pnl', 0):,.0f} across "
            f"{test.get('num_trades', 0)} trades (profit factor "
            f"{test.get('profit_factor', 0):.2f}, expectancy ₹{test.get('expectancy', 0):,.0f}). "
            "After realistic costs the edge doesn't survive on unseen data — which is the "
            "normal result for most simple rules. Not a strategy to risk money on.")
    else:  # PROMISING
        lines.append(
            f"Out-of-sample it made ₹{test.get('net_pnl', 0):,.0f} across "
            f"{test.get('num_trades', 0)} trades (profit factor "
            f"{test.get('profit_factor', 0):.2f}). It held up on data it never saw — "
            "promising, but paper-trade it live before risking real capital. One clean "
            "backtest is not proof.")

    lines.append(f"(Full-period net: ₹{full.get('net_pnl', 0):,.0f} over "
                 f"{full.get('num_trades', 0)} trades.)")
    return " ".join(lines)


def explain_result(spec: StrategySpec, result: dict, settings: Settings | None = None,
                   use_llm: bool = True) -> str:
    """A short, honest plain-English explanation of the verdict."""
    settings = settings or get_settings()
    if use_llm and settings.anthropic_api_key:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            facts = _template_explanation(spec, result)
            msg = client.messages.create(
                model=_MODEL,
                max_tokens=400,
                system=("You explain a trading-strategy backtest to a retail investor in 2-4 "
                        "plain sentences. Be honest and never hype: if the verdict is NO EDGE or "
                        "INSUFFICIENT DATA, say so plainly. Base your answer only on the facts given."),
                messages=[{"role": "user", "content": facts}],
            )
            return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
        except Exception:  # noqa: BLE001
            pass
    return _template_explanation(spec, result)
