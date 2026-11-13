import numpy as np
import pandas as pd

from pead01.phase2 import build_panel, mark_dates, minute_panel, price_return, select_controls
from pead01.phase2_report import common_ids


def test_control_fixed_bands_and_deterministic_ties():
    candidates = pd.DataFrame({"cap": [2e10, 2e10, 2e10, 3.01e10],
                               "Va": [8e7, 8e7, 8e7, 8e7]}, index=["E", "B", "A", "C"])
    pool, match = select_controls(candidates, "E", 2e10, 8e7)
    assert pool.index.tolist() == ["A", "B", "C"]
    assert match == "A"
    assert select_controls(candidates, "E", 2e10, 1e9)[1] is None


def test_entry_session_is_day_one_and_common_set_requires_every_point():
    dates = pd.to_datetime(["2024-11-01", "2024-11-05", "2024-11-06", "2024-11-07"])
    assert mark_dates(dates, dates[1], [1, 3, 5]) == [dates[1], dates[3], pd.NaT]
    frame = pd.DataFrame({"event_id": ["x", "x", "y", "y", "z", "z"],
                          "day": [1, 3, 1, 3, 1, 1], "ret": [0., .1, 0., np.nan, .1, .1]})
    assert common_ids(frame, "day", "ret", [1, 3]).tolist() == ["x"]


def test_invalid_adjustment_chain_or_untraded_open_is_missing():
    entry = pd.DataFrame({"open": [100., 100., np.nan], "factor_errors": [0, 1, 0]})
    exit = pd.DataFrame({"close": [110., 110., 110.], "factor_errors": [0, 2, 0]})
    result = price_return(entry, exit)
    np.testing.assert_allclose(result, [.1, np.nan, np.nan], equal_nan=True)


def test_intraday_elapsed_time_includes_overnight():
    event = pd.DataFrame({"event_id": ["x"], "security_code": ["72030"],
                          "announcement_date": pd.to_datetime(["2024-11-05"]),
                          "announcement_datetime": pd.to_datetime(["2024-11-05 15:30"]).tz_localize("Asia/Tokyo"),
                          "announcement_bucket": ["after_close"]})
    minute = pd.DataFrame({"event_id": ["x"], "session": pd.to_datetime(["2024-11-06"]), "entry_minute": [541]})
    assert minute_panel(minute, event).elapsed_minutes.iloc[0] == 1051


def test_match_excludes_known_disclosures_and_keeps_match_when_exit_missing():
    dates = pd.bdate_range("2024-01-15", periods=4)
    securities = ["event", "early", "late", "other"]
    prices = pd.DataFrame(index=pd.MultiIndex.from_product([dates, securities], names=["Date", "Code"]))
    prices = prices.assign(open=100., close=110., factor_errors=0, MktCap=20000., Va=5e7)
    prices.loc[(dates[0], "other"), "Va"] = 8e7
    prices.loc[(dates[2], "late"), "close"] = np.nan
    universe = {dates[0]: pd.DataFrame({"S33Nm": "sector"}, index=securities)}
    topix = pd.DataFrame({"Date": dates, "O": 100., "C": 101.})
    disclosures = pd.DataFrame({"Code": ["event", "early", "late"],
                                "DiscDate": [dates[1], dates[2], dates[2]],
                                "DiscTime": ["15:30", "08:00", "15:30"]})
    events = pd.DataFrame({"event_id": ["e"], "announcement_date": [dates[1]], "next_open_date": [dates[2]],
                           "security_code": ["event"], "sector": ["sector"],
                           "market_cap": [2e10], "prior_turnover": [5e7]})
    day1 = build_panel(events, universe, prices, topix, dates, disclosures).iloc[0]
    assert day1.control == "late"
    assert day1.industry_candidates == 2
    assert day1.industry_observed == 1
    assert np.isnan(day1.matched)
