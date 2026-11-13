import pandas as pd
import pytest

from pead01.phase5 import market_features
from pead01.phase5_execution import audit_point, delayed_trade, portfolio


def test_audit_separates_break_and_missing_etf():
    stock = pd.DataFrame({"O": [100], "C": [102], "Vo": [10]}, index=[804])
    assert audit_point(stock, stock.iloc[:0], 800, 5, 930, True) == "etf_no_print"
    assert audit_point(stock, stock, 689, 15, 930, True) == "scheduled_break"
    assert audit_point(stock, stock, 901, 60, 930, True) == "session_ended"


def test_entry_after_signal_and_missing_never_filled():
    stock = pd.DataFrame({"O": [100, 101, 105], "C": [101, 102, 106], "Vo": [10, 10, 20]},
                         index=[804, 806, 859])
    assert delayed_trade(stock, 800, 1, 930) == (805, 806, 860, 101, 106)
    assert delayed_trade(stock, 800, 5, 930) is None


def test_capacity_uses_prior_turnover_and_idle_days_remain():
    days = pd.date_range("2025-01-01", periods=2)
    trade = pd.DataFrame({"session": [days[0]], "entry_minute": [806], "exit_minute": [860],
                          "security_code": ["a"], "event_id": ["e"], "known_turnover": [10_000_000],
                          "gross": [.01]})
    result = portfolio(trade, days, 10, .01)
    assert result.deployed.tolist() == [100_000, 0]
    assert result.net.tolist() == pytest.approx([.000009, 0])


def test_volatility_threshold_excludes_current_session():
    days = pd.date_range("2025-01-01", periods=150)
    close = pd.DataFrame({"C": range(100, 250)}, index=days)
    volume = pd.Series(100, index=days)
    original = market_features(close, volume)
    close.iloc[-1] *= 2
    revised = market_features(close, volume)
    assert revised.vol_threshold.iloc[-1] == original.vol_threshold.iloc[-1]
    assert revised.vol_20.iloc[-1] != original.vol_20.iloc[-1]
