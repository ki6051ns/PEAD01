import numpy as np
import pandas as pd
import pytest

from pead01.phase3 import historical_rank, select
from pead01.phase3_portfolio import simulate, trade_paths
from pead01.phase3_signals import daily_signals, membership


def test_daily_initial_excess_and_next_open():
    days = pd.bdate_range("2025-01-06", periods=4)
    prices = pd.DataFrame({"open": [100, 110, 115, 118], "close": [100, 112, 116, 120],
                           "factor_errors": 0, "limit_flag": False},
                          index=pd.MultiIndex.from_product([days, ["x"]], names=["Date", "Code"]))
    index = pd.DataFrame({"O": [100, 101, 102, 103], "C": [100, 104, 103, 105]}, index=days)
    events = pd.DataFrame({"event_id": ["event"], "security_code": ["x"], "baseline_date": [days[0]],
                           "first_session": [days[1]], "next_open_date": [days[2]]})
    signals = daily_signals(events, prices, index, days, set()).set_index("method")
    assert signals.at["A", "initial_excess"] == pytest.approx(.08)
    assert signals.at["A", "entry_date"] == days[2]
    assert signals.at["C", "entry_date"] == days[3]
    assert (signals.signal_time < signals.order_time).all()
    assert (signals.order_time < signals.fill_time).all()


def test_membership_does_not_infer_from_missing_scale():
    assert membership(pd.Series(["TOPIX Small 2", "-", None, "unknown"])).tolist() == [
        "topix", "non_topix", None, None,
    ]


def test_rank_uses_only_earlier_days():
    d1, d2 = pd.bdate_range("2025-01-06", periods=2)
    signals = pd.DataFrame({"method": "A", "signal_date": [d1] * 250 + [d2] * 2,
                            "initial_excess": [0.] * 250 + [1., -.1]})
    ranks = historical_rank(signals)
    assert ranks.iloc[:250].isna().all()
    assert ranks.iloc[-2:].tolist() == [1., 0.]


def test_quantile_filter_respects_direction():
    trades = pd.DataFrame({"side": [1, -1, 1], "rank": [.95, .05, .05]})
    assert select(trades, "all", "LS", "q10").index.tolist() == [0, 1]


def test_costs_cash_day_and_overlap():
    dates = pd.bdate_range("2025-01-06", periods=3)
    row = dict(event_id="a", code="x", sector="s", universe="topix", loanable=True, start=0, end=1,
               side=1, beta=1., adv=1e9, bar_turnover=np.nan, fill_time=dates[0], entry_date=dates[0],
               end_time=dates[1], closed=True, limit_day=False, marks=np.array([1.1, 1.2]))
    trades = pd.DataFrame([row, {**row, "event_id": "b", "start": 1}])
    index = pd.DataFrame({"O": 100, "C": 100}, index=dates)
    daily, fills, rejects = simulate(trades, dates, index, "L", 20)
    repeated, repeat_fills, _ = simulate(trades.iloc[::-1], dates, index, "L", 20)
    pd.testing.assert_frame_equal(daily, repeated)
    pd.testing.assert_frame_equal(fills, repeat_fills)
    assert len(fills) == 1
    assert rejects["overlap"] == 1
    assert daily["nav"].iloc[-1] == pytest.approx(1 + .002 - .001 * (.01 + .012))
    assert daily["return"].iloc[-1] == 0


def test_missing_exit_price_is_retried_without_fabricated_fill():
    dates = pd.bdate_range("2025-01-06", periods=3)
    quotes = {"x": (np.array([np.nan, 1.2, 1.2]), np.zeros(3), np.zeros(3))}
    trades = pd.DataFrame([dict(event_id="a", method="A", security_code="x", sector="s", universe="topix",
        loanable=True, entry_date=dates[0], factor_errors=0, initial_excess=.01, entry=1., beta=1.,
        prior_turnover=1e9, bar_turnover=np.nan, forecast_revision=.01, fill_time=dates[0], limit_day=False)])
    path = trade_paths(trades, quotes, dates, set(), 1).iloc[0]
    assert path.end == 1
    assert path.closed
    assert path.marks.tolist() == [1., 1.2]


def test_close_entry_begins_holding_on_following_session():
    dates = pd.bdate_range("2026-08-03", periods=3)
    quotes = {"x": (np.array([1., 1.1, 1.2]), np.zeros(3), np.zeros(3))}
    trades = pd.DataFrame([dict(event_id="b", method="B1445", security_code="x", sector="s", universe="topix",
        loanable=True, entry_date=dates[0], factor_errors=0, initial_excess=.02, entry=1., beta=1.,
        prior_turnover=1e9, bar_turnover=1e8, forecast_revision=.03,
        fill_time=dates[0] + pd.Timedelta(hours=15, minutes=30), limit_day=False)])
    path = trade_paths(trades, quotes, dates, set(), 1).iloc[0]
    assert path.target == 1
    assert path.end_time == dates[1] + pd.Timedelta(hours=15, minutes=30)
    assert path.marks.tolist() == [1., 1.1]
