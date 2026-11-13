from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from pead01.daily import build_daily, prepare_daily, session_close
from pead01.events import FIN_COLUMNS, build_events
from pead01.minute import build_minute, minute_returns, valid_minutes


def financial(date, number, kind="FY", **values):
    row = dict.fromkeys(FIN_COLUMNS)
    row.update(DiscDate=date, DiscTime="15:00:00", Code="72030", DiscNo=number,
               DocType=f"{kind}FinancialStatements_Consolidated_JP", CurPerType=kind)
    row.update(values)
    return row


def test_forecast_must_predate_event_and_match_target():
    rows = [
        financial("2024-05-10", "a", CurPerEn="2024-03-31", NxtFYEn="2025-03-31", NxFOP=100),
        financial("2025-05-10", "b", DocType="EarnForecastRevision", CurFYEn="2025-03-31", FOP=200),
        financial("2025-05-10", "c", CurPerEn="2025-03-31", OP=120, NxFOP=500),
        financial("2025-05-11", "d", CurPerEn="2025-03-31", OP=140, DiscTime=None),
    ]
    events = build_events(pd.DataFrame(rows)).set_index("event_id")
    assert events.loc["jq:72030:c", "company_surprise_op"] == pytest.approx(.20)
    assert events.loc["jq:72030:c", "actual_operating_profit"] == 120
    assert events.loc["jq:72030:d", "repeat_period"]
    assert pd.isna(events.loc["jq:72030:d", "announcement_datetime"])


def test_split_factor_on_ex_date_and_zero_volume_price():
    bars = pd.DataFrame({
        "Date": pd.to_datetime(["2024-11-01", "2024-11-05", "2024-11-06"]),
        "Code": ["72030"] * 3, "O": [1000, 500, 500], "H": [1000, 500, 500],
        "L": [1000, 500, 500], "C": [1000, 500, 500], "Vo": [10, 5, 0],
        "AdjFactor": [1, .5, 1], "Va": [10000, 2500, 0], "MktCap": [1, 1, 1],
        "UL": [0, 0, 0], "LL": [0, 0, 0],
    })
    result = prepare_daily(bars)
    assert result.close.iloc[1] / result.close.iloc[0] == 1
    assert np.isnan(result.open.iloc[2])


def test_minute_excludes_disclosure_minute_and_does_not_carry_last_price():
    day = pd.Timestamp("2024-11-05")
    bars = pd.DataFrame({"O": [100, 120, 125, 131], "C": [100, 120, 126, 131]},
                        index=[782, 783, 784, 930])
    event = SimpleNamespace(event_id="test", security_code="72030", announcement_date=day,
                            announcement_datetime=pd.Timestamp("2024-11-05 13:03", tz="Asia/Tokyo"),
                            first_session=day)
    returns = {r["horizon"]: r for r in minute_returns(event, {(day, "72030"): bars}, {}, set())}
    assert returns["first_trade"]["entry_minute"] == 784
    assert returns["first_trade"]["total"] == .25
    assert "5" not in returns
    assert returns["same_day_close"]["target_minute"] == 930


def test_exchange_hours_extension():
    assert session_close(pd.Timestamp("2024-11-01")) == 900
    assert session_close(pd.Timestamp("2024-11-05")) == 930
    assert valid_minutes(np.array([690, 691, 749, 750, 924, 925, 929, 930]), 930).tolist() == [
        True, False, False, True, True, False, False, True,
    ]
    assert valid_minutes(np.array([900, 900]), np.array([900, 930])).tolist() == [True, True]


def test_daily_close_event_uses_next_session_and_pre_event_attributes():
    dates = pd.to_datetime(["2024-11-01", "2024-11-05", "2024-11-06", "2024-11-07"])
    events = build_events(pd.DataFrame([
        financial("2024-11-05", "a", DiscTime="15:30:00", CurPerEn="2024-09-30"),
    ]))
    prices = pd.DataFrame({"Date": dates, "Code": "72030", "O": [100, 108, 120, 122],
                           "C": [100, 110, 123, 124], "H": [101, 111, 124, 125],
                           "L": [99, 107, 119, 121], "Vo": 10, "Va": 1000,
                           "AdjFactor": 1, "MktCap": [1, 2, 3, 4], "UL": 0, "LL": 0})
    master = pd.DataFrame({"Date": dates, "Code": "72030", "ProdCat": "011", "Mkt": "0111",
                           "CoName": ["Old name", "New name", "New name", "New name"],
                           "S33Nm": "Transport"}).set_index(["Date", "Code"])
    index = pd.DataFrame({"Date": dates, "O": 1000, "C": 1000})
    calendar = pd.DataFrame({"Date": dates, "HolDiv": "1"})
    events, returns = build_daily(events, prepare_daily(prices), master, index, calendar)
    marks = returns.set_index("horizon")
    assert events.company_name.iloc[0] == "Old name"
    assert events.market_cap.iloc[0] == 1e6
    assert events.baseline_date.iloc[0] == dates[0]
    assert marks.at["1", "target_date"] == dates[2]
    assert marks.at["next_open", "total_excess"] == pytest.approx(.20)
    assert pd.isna(marks.at["next_open", "post"])
    assert marks.at["1", "post_excess"] == pytest.approx(.025)


def test_minute_build_accepts_multiple_disclosures_on_same_session():
    day = pd.Timestamp("2026-08-03")
    events = pd.DataFrame({"event_id": ["a", "b"], "security_code": "72030",
                           "first_session": day, "baseline_date": pd.NaT, "announcement_date": day,
                           "universe_status": "tse_common",
                           "announcement_datetime": day.tz_localize("Asia/Tokyo") + pd.Timedelta(hours=13)})
    daily = pd.DataFrame(columns=["Date", "Code", "close", "factor_level", "factor_errors"]).set_index(["Date", "Code"])
    minute = pd.DataFrame({"Date": ["2026-08-03"], "Time": ["13:01"], "Code": ["72030"],
                           "O": [120], "C": [121], "Vo": [10]})
    calendar = pd.DataFrame({"Date": [day], "HolDiv": ["1"]})
    returns, bad = build_minute(events, daily, calendar, [minute])
    assert bad == 0
    assert returns.event_id.tolist() == ["a", "b"]
    assert returns.entry_minute.tolist() == [781, 781]
