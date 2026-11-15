import json
from pathlib import Path

import numpy as np
import pandas as pd

from pead01.phase6_daily_wf import observations
from pead01.phase8 import replay_condition
from pead01.phase8_wf import choose, schedules, score_paths, select, windows


CFG = json.loads((Path(__file__).parents[1]/"phase8.json").read_text(encoding="utf-8-sig"))


def test_common_wf_and_fixed_candidate_training_window():
    grids = dict(schedules(2440, CFG))
    assert grids[0][0] == (1936, 1999)
    assert grids[21][0] == (1936, 1957)
    for folds in grids.values():
        assert folds[0][0] == 1936 and folds[-1][1] == 2440
        assert all(a[1] == b[0] for a, b in zip(folds, folds[1:]))
    assert windows(1936, 60, 0, "A", 756) == ((0, 1876), None)
    assert windows(1936, 60, 45, "A", 756) == ((0, 1771), (1831, 1876))
    assert windows(1936, 60, 756, "A", 756) == ((0, 1060), (1120, 1876))
    for duration in CFG["validation_days"]:
        train, validation = windows(1936, 60, duration, "B", 756)
        assert train == (0, 1060)
        if validation:
            assert validation[0] >= train[1]+60
            assert validation[1] == 1876


def test_rerank_screen_and_fixed_minimums():
    train = pd.DataFrame({"fills": [30, 31, 29, 300], "sharpe": [2., 1., 3., 0.]})
    validation = pd.DataFrame({"fills": [8, 9, 100, 7], "sharpe": [0., 5., 10., 100.]})
    for rule, expected in [("rerank", [1, 0]), ("screen", [0, 1]), ("direct", [0, 1, 3])]:
        shortlist, best = choose(train, validation if rule != "direct" else None, rule, CFG)
        assert shortlist.tolist() == [0, 1, 3]
        assert best.tolist() == expected
    assert choose(train, validation.assign(fills=7), "screen", CFG)[1].empty


def setup_paths():
    days = pd.bdate_range("2025-01-06", periods=49)
    common = dict(method="Close→Open", entry="O", exit_price="C", hold=40,
                  sector="industry", adv=1e9, exit_minute=930, loanable=True)
    df = pd.DataFrame([
        dict(**common, start=start, signal_time=days[signal], end=end, closed=closed,
             event_id=f"{code}|Close→Open|40", code=code, gap=gap,
             fill_time=days[start]+pd.Timedelta(hours=9), marks=np.linspace(1, 1.05, end-start+1))
        for code, start, signal, end, closed, gap in [
            ("x", 1, 0, 41, True, .10), ("y", 2, 1, 42, True, -.10),
            ("z", 2, 1, 48, False, .10), ("v", 4, 3, 47, True, .10)]])
    return days, df


def test_maturity_sweep_matches_phase6_strict_cutoffs():
    days, trades = setup_paths()
    ranges = [(0, 41), (0, 42), (0, 43), (0, 49), (1, 43), (2, 49)]
    _, reference, trace = observations(trades, CFG, days, ranges)
    _, audit, actual = score_paths(trades, CFG, days, ranges, 0)
    pd.testing.assert_series_equal(audit.fills, trace.fills)
    pd.testing.assert_series_equal(audit.purged, trace.purged)
    np.testing.assert_allclose(audit.sharpe, trace.sharpe)
    for interval, series in actual.items():
        np.testing.assert_allclose(series, reference[interval])
    assert audit.query("id == 0").fills.tolist() == [0, 1, 1, 2, 0, 1]


def test_common_book_blank_netting_and_cash():
    days, trades = setup_paths()
    specs, _, _ = score_paths(trades, CFG, days, [(0, 49)], 0)
    history = pd.DataFrame([
        (1, 49, 0, "single", 0, 1.), (1, 49, 0, "ensemble", 0, .5),
        (1, 49, 10, "ensemble", 0, .5), (1, 49, 0, "cash", -1, 0.)
    ], columns=["start", "end", "blank", "mode", "id", "weight"])
    daily, journal = replay_condition(trades, specs, history, days, CFG)
    pivot = daily.pivot(index="date", columns="mode", values="net")
    np.testing.assert_array_equal(pivot.ensemble, pivot.single)
    assert pivot.cash.eq(0).all()
    assert journal.loc[journal["mode"].eq("single")].entry.sum() == 3
    assert not journal["mode"].eq("cash").any()
    money_market, empty = replay_condition(trades, specs, history.loc[history["mode"].eq("cash")], days, CFG)
    assert empty.empty and money_market.net.eq(0).all()


def test_forward_results_do_not_change_selection_or_weights():
    cfg = {**CFG, "blanks": [0], "validation_days": [0, 45]}
    days, trades = setup_paths()
    specs, _, _ = score_paths(trades, cfg, days, [(0, 49)], 0)
    ids = specs.id
    train = pd.DataFrame({"fills": 50, "purged": 1, "last_label": 225,
                          "sharpe": np.linspace(2, 1, len(ids))}, index=ids)
    val = train.assign(sharpe=train.sharpe.iloc[::-1].to_numpy(), last_label=270)
    diagnostic = pd.DataFrame({"return": np.linspace(1, 2, len(ids)), "fills": 12}, index=ids)
    scores = {(0, 255): train, (255, 300): val, (300, 363): diagnostic}
    streams = {(c, 0, 255): np.cos(np.arange(255) + c) for c in ids}
    selection, original = select(specs, scores, streams, [(300, 363)], cfg, "A", 45, "rerank")
    scores[300, 363] = diagnostic.assign(**{"return": -diagnostic["return"]})
    repeated, modified = select(specs, scores, streams, [(300, 363)], cfg, "A", 45, "rerank")
    pd.testing.assert_frame_equal(selection, repeated)
    np.testing.assert_allclose(original.forward_return, -modified.forward_return)
