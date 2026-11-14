from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from pead01.phase6_book import book
from pead01.phase6_grid import prepare, spec
from pead01.phase6_report import effective, rank, weights
from pead01.phase6_batch import run_stages
from pead01.phase6 import chunks


def test_shared_cash_and_same_security_netting():
    config = {"capital": 100, "position_limit": 1}
    days = pd.date_range("2026-01-01", periods=2)
    row = SimpleNamespace(start=0, end=0, minute=540, exit_minute=900, code="x", sector="s",
                          event_id="a", capacity=.1, marks=np.array([1.1]), frequency="daily",
                          loanable=True, cost=20, closed=True, hedge=False)
    neutral, _ = book([(row, 1, .5), (row, -1, .5)], days, config)
    assert not neutral.any()
    same, pos = book([(row, 1, .5), (row, 1, .5)], days, config)
    assert len(pos) == 1
    np.testing.assert_allclose(same[:, 5], [.001-.000021, 0])


def test_training_rank_ignores_following_returns():
    matrix = np.zeros((2, 4, 6))
    matrix[:, :, 4] = 1
    matrix[:, :, 0] = [[1, 2, 1, 2], [-2, 1, 100, 101]]
    assert rank(matrix, 0, 2, 2).tolist() == [0, 1]


def test_correlated_copies_do_not_increase_effective_count():
    sample = np.array([[1, 2, 3], [1, 2, 3]], dtype=float)
    assert np.isclose(effective(sample)[0], 1)
    for style in ("equal", "inverse", "shrink", "parity", "max_sharpe"):
        out = weights(sample, style)
        assert np.isclose(out.sum(), 1) and (out >= 0).all()
    assert spec("A", 20)["id"] == spec("A", "20")["id"]


def test_minute_preparation_preserves_path_capacity_inputs():
    columns = ["security_code", "sector", "universe", "loanable", "beta", "market_cap", "past_size",
               "market_20", "vol_20", "vol_threshold", "OP_revision_amount", "EPS_revision_amount",
               "OP_company_surprise", "EPS_company_surprise", "OP_series_surprise", "op_progress_change",
               "volume_burst_5", "first5_prints", "announcement_bucket", "known_busy", "historical_rank"]
    data = pd.DataFrame({c: [np.nan] for c in columns}, index=["event"])
    data.attrs["ranks"] = pd.Series([.95], index=pd.MultiIndex.from_tuples([("event", "I5")]))
    paths = pd.DataFrame({"event_id": ["event"], "adv20": [100.], "prior_turnover": [80.],
                          "method": ["I5"], "gap": [.01], "signal_time": pd.to_datetime(["2026-01-01 09:10"]),
                          "marks": [np.array([1.01])]})
    assert prepare(paths, data, {}).adv.iloc[0] == 100.
    assert prepare(paths, data, {}).historical_rank.iloc[0] == .95


def test_stages_resume_from_last_completed_marker(tmp_path):
    calls = []

    def run(stage):
        calls.append(stage)
        if stage == "ensemble" and calls.count(stage) == 1:
            raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        run_stages(run, {}, "all", True, lambda **_: None, tmp_path)
    run_stages(run, {}, "all", True, lambda **_: None, tmp_path)
    assert calls == ["paths", "search", "ensemble", "ensemble", "walkforward", "report"]


def test_screen_workers_and_checkpoint_are_equal(tmp_path, monkeypatch):
    from pead01 import phase6

    dates = pd.date_range("2025-01-06", periods=2)
    candidate = spec("A", 1)
    frame = pd.DataFrame(dict(event_id=["e"], method=["A"], hold=[1], start=[0], end=[0],
                              gap=[.02], capacity=[.01], cost=[20], closed=[True], last=[1.02],
                              marks=[np.array([1.02])], frequency=["daily"], adv=[1e8], loanable=[True]))
    monkeypatch.setattr(phase6, "prepare", lambda frame, *_: frame)
    monkeypatch.setattr(phase6, "available_specs", lambda *_: [candidate, spec("A", 1, direction="ls")])
    config = dict(capital=1e8, position_limit=1e6)
    output = []
    for workers in (1, 2):
        directory = tmp_path / str(workers)
        directory.mkdir()
        args = (frame, pd.DataFrame({"sector": ["x"]}), dates, np.array([[.01, .02], [.01, .02]]),
                config, directory, {})
        specs, paths = chunks(*args, workers=workers)
        with np.load(paths[0]) as saved:
            output.append(saved["values"])
        monkeypatch.setattr(phase6, "prepare", lambda *_: pytest.fail("unexpected cache miss"))
        assert chunks(*args, workers=workers) == (specs, paths)
        monkeypatch.setattr(phase6, "prepare", lambda frame, *_: frame)
    np.testing.assert_array_equal(*output)
