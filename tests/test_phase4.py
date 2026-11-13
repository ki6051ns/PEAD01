from types import SimpleNamespace

import numpy as np
import pandas as pd

from pead01.phase4_financial import COLUMNS, financial_features, ratio, sign_change
from pead01.phase4_paths import paths_for_event, trading_clock


def test_lunch_and_preclosing_do_not_count_as_continuous_trading():
    assert trading_clock([689, 690, 749, 750, 751, 925, 930]).tolist() == [149, 150, 150, 150, 151, 325, 325]


def test_missing_print_and_release_minute_are_excluded():
    day = pd.Timestamp("2026-02-12")
    event = SimpleNamespace(event_id="a", announcement_date=day, first_session=day,
        announcement_datetime=(day + pd.Timedelta(hours=13)).tz_localize("Asia/Tokyo"))
    stock = pd.DataFrame({"O": [100, 150, 110, 112, 118], "C": [100, 150, 110, 112, 118],
                          "H": [100, 150, 110, 112, 118], "L": [100, 150, 110, 112, 118],
                          "Va": 1000, "Vo": 10}, index=[779, 780, 781, 785, 795])
    market = stock.assign(O=100, C=100)
    rows, meta = paths_for_event(event, stock, market, (100, 100), 930)
    assert meta["first_minute"] == 781
    assert np.isclose(meta["initial_excess"], .12)
    assert "wall_30" not in [row[1] for row in rows]


def test_small_denominator_and_profit_transition():
    assert np.isnan(ratio(10, .01, 1.))
    assert ratio(10, -10, 1.) == 2
    assert sign_change(10, -10) == "to_profit"


def test_forecast_uses_prior_day_same_fiscal_target():
    rows = []
    for number, day, target, op, kind in [
        ("a", "2025-02-12", "2025-03-31", 2e6, "EarnForecastRevision"),
        ("b", "2025-02-13", "2026-03-31", 9e6, "EarnForecastRevision"),
        ("c", "2025-02-14", "2025-03-31", 8e6, "EarnForecastRevision"),
        ("d", "2025-02-14", "2025-03-31", 3e6, "3QFinancialStatements_Consolidated_JP"),
    ]:
        row = dict.fromkeys(COLUMNS, np.nan)
        row.update(Code="72030", DiscDate=day, DiscTime="15:30:00", DiscNo=number,
                   DocType=kind, CurFYEn=target, CurPerType="3Q", FOP=op)
        rows.append(row)
    events = pd.DataFrame({"event_id": ["jq:72030:d"], "announcement_date": pd.to_datetime(["2025-02-14"])})
    result = financial_features(pd.DataFrame(rows), events).iloc[0]
    assert result.OP_revision_before == 2e6
    assert result.OP_revision_rate == .5
