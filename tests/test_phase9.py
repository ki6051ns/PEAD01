import numpy as np
import pandas as pd
import pytest

from pead01.phase8_wf import HISTORY, PARAMETERS
from pead01.phase9 import bounds, histories, run_book, session_positions, training_interval


def test_fixed_wf_and_six_year_window_do_not_shorten():
    dates = pd.date_range("2020-01-01", periods=2441)
    cfg = {"first_wf": dates[1937].isoformat(), "last_wf": dates[-1].isoformat(),
           "wf_sessions": 504, "update_days": 63}
    folds = bounds(dates, cfg)
    assert len(folds) == 8 and folds[0] == (1937, 2000) and folds[-1] == (2378, 2441)
    assert training_interval(1937, 1512, 10) == (415, 1927)
    assert training_interval(1937, 0, 10) == (0, 1927)
    assert training_interval(1937, 252, 10, 45) == (1620, 1872)
    with pytest.raises(ValueError, match="Insufficient training"):
        training_interval(1521, 1512, 10)


def test_map_requires_every_session_not_just_endpoints():
    old = pd.date_range("2024-10-01", periods=10)
    assert session_positions(old, old, [(0, 9)]) == [(0, 9)]
    with pytest.raises(ValueError, match="inside a legacy WF block"):
        session_positions(old, old.delete(2), [(0, 9)])


def test_fixed_windows_change_choices_using_only_pre_wf_scores():
    candidates = pd.DataFrame([
        (0, "Close→Open", "O", 10, "C", "long", 0),
        (1, "Close→Open", "O", 20, "C", "long", 0),
        (2, "Open→Close", "O", 20, "C", "short", 0),
    ], columns=["id", *PARAMETERS])
    rank = lambda xs: pd.DataFrame({"fills": [30, 32, 33], "sharpe": xs}, index=candidates.id)
    score = {(38, 290): rank([3, 1, 2]), (0, 290): rank([1, 2, 3])}
    h = histories(candidates, score, {}, [(300, 363)], {"min_train_fills":30},
                  [252, 0], [10], "primary")
    assert h.query("mode == 'primary_single_252'").id.tolist() == [0]
    assert h.query("mode == 'primary_neighbor_252'").id.tolist() == [0, 1]
    assert h.query("mode == 'primary_neighbor_0'").id.tolist() == [2]
    np.testing.assert_allclose(h.groupby("mode").weight.sum(), 1)


def test_cash_only_book_has_dated_nav_and_no_executions():
    sessions = pd.bdate_range("2025-01-01", periods=5)
    s = pd.DataFrame([(0, 5, 10, "cash", -1, 0.)], columns=HISTORY)
    specs = pd.DataFrame(columns=["id", *PARAMETERS])
    f, j, x = run_book(pd.DataFrame(columns=PARAMETERS[:4]), specs, s, sessions,
                       {"capital":1e8, "cost_bp":20, "position_limit":1e6})
    np.testing.assert_array_equal(f.nav, 1e8)
    assert j.empty and x.empty
