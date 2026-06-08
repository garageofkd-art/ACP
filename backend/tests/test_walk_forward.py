from datetime import date, datetime, timedelta

import pandas as pd

from app.backtest.optimizer import split_by_date


def _two_day_frame() -> pd.DataFrame:
    rows = []
    for d in (datetime(2026, 6, 1, 9, 15), datetime(2026, 6, 2, 9, 15)):
        for i in range(5):
            ts = d + timedelta(minutes=i)
            rows.append({"ts": ts, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 10})
    return pd.DataFrame(rows)


def test_split_is_chronological_and_disjoint():
    train, test = split_by_date({"A": _two_day_frame()}, train_frac=0.5)
    assert all(t.date() == date(2026, 6, 1) for t in train["A"]["ts"])
    assert all(t.date() == date(2026, 6, 2) for t in test["A"]["ts"])


def test_split_empty_data():
    train, test = split_by_date({}, train_frac=0.6)
    assert train == {} and test == {}
