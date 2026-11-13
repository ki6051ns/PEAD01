"""Event-day alignment and daily traded-price returns."""
import numpy as np
import pandas as pd

DAILY_COLUMNS = ["Date", "Code", "O", "H", "L", "C", "Vo", "Va", "AdjFactor", "MktCap", "UL", "LL"]
MASTER_COLUMNS = ["Date", "Code", "CoName", "S33Nm", "Mkt", "ProdCat"]
TSE_MARKETS = ["0101", "0102", "0104", "0105", "0106", "0111", "0112", "0113"]
HORIZONS = (1, 3, 5, 10, 20)


def session_close(day, half_day=False):
    if half_day:
        return 11 * 60 + 30
    return 900 if day < pd.Timestamp("2024-11-05") else 930


def prepare_daily(prices):
    prices = prices.drop_duplicates().sort_values(["Code", "Date"]).copy()
    for column in ("O", "H", "L", "C", "Vo", "Va", "AdjFactor", "MktCap", "UL", "LL"):
        prices[column] = pd.to_numeric(prices[column], errors="coerce")
    prices["bad_ohlc"] = prices.Vo.gt(0) & (
        (~np.isfinite(prices[["O", "H", "L", "C"]])).any(axis=1)
        | prices[["O", "H", "L", "C"]].le(0).any(axis=1)
        | prices.H.lt(prices[["O", "L", "C"]].max(axis=1))
        | prices.L.gt(prices[["O", "C"]].min(axis=1))
    )
    valid = prices.Vo.gt(0) & ~prices.bad_ohlc
    # Invalid factors break the adjustment chain within a window.
    factor_valid = prices.AdjFactor.gt(0) & np.isfinite(prices.AdjFactor)
    prices["factor_errors"] = (~factor_valid).groupby(prices.Code).cumsum()
    prices["factor_level"] = prices.AdjFactor.where(factor_valid, 1).groupby(prices.Code).cumprod()
    for raw, adjusted in [("O", "open"), ("C", "close")]:
        prices[adjusted] = prices[raw].where(valid & prices[raw].gt(0)) / prices.factor_level
    prices["limit_flag"] = prices.UL.eq(1) | prices.LL.eq(1)
    return prices.set_index(["Date", "Code"], verify_integrity=True)


def lookup(frame, dates, codes):
    index = pd.MultiIndex.from_arrays([dates, codes], names=["Date", "Code"])
    return frame.reindex(index).reset_index(drop=True)


def build_daily(events, prices, master, topix, calendar):
    sessions = pd.DatetimeIndex(calendar.loc[calendar.HolDiv.isin(["1", "2"]), "Date"].unique()).sort_values()
    half = set(calendar.loc[calendar.HolDiv.eq("2"), "Date"])
    if not prices.index.get_level_values("Date").isin(sessions).all():
        raise ValueError("Daily bars outside JPX cash sessions")
    ix = sessions.searchsorted(events.announcement_date)
    next_ix = sessions.searchsorted(events.announcement_date, side="right")

    def dates(indices):
        return pd.Series(sessions.take(indices.clip(0, len(sessions) - 1))).where(
            (indices >= 0) & (indices < len(sessions))
        )

    attribute_date = dates(ix - 1)
    code = events.security_code
    attributes = lookup(master, attribute_date, code)
    # A newly listed security can use a dated listing row for universe eligibility.
    same_day = lookup(master[["Mkt", "ProdCat"]], events.announcement_date, code)
    eligible = attributes.ProdCat.fillna(same_day.ProdCat).eq("011") & attributes.Mkt.fillna(same_day.Mkt).isin(TSE_MARKETS)
    events["universe_status"] = np.select(
        [eligible, attributes.Mkt.notna() | same_day.Mkt.notna()], ["tse_common", "other"], default="unmatched"
    )
    timing = events.announcement_datetime.dt.hour * 60 + events.announcement_datetime.dt.minute
    close = events.announcement_date.map(lambda d: session_close(d, d in half))
    on_session = next_ix > ix
    after = timing.ge(close) | ~on_session
    category = np.select(
        [timing.isna(), ~on_session, after, timing.lt(540), timing.lt(690),
         timing.lt(750), (events.announcement_date.ge("2024-11-05") & timing.ge(925))],
        ["unknown", "non_session", "after_close", "before_open", "morning", "lunch", "closing_auction"],
        default="afternoon",
    )
    first_ix = np.where(after | timing.isna(), next_ix, ix)
    open_ix = np.where(on_session & timing.lt(540), ix, next_ix)
    pre_date = dates(np.where(on_session & timing.gt(close), ix, ix - 1))
    prior_attributes = lookup(prices, attribute_date, code)
    pre = lookup(prices, pre_date, code)
    entry = lookup(prices, dates(open_ix), code)
    events = events.assign(
        company_name=attributes.CoName, sector=attributes.S33Nm,
        attributes_date=attribute_date.where(attributes.Mkt.notna()), market_cap=prior_attributes.MktCap * 1e6,
        prior_price=prior_attributes.C.where(prior_attributes.close.notna()),
        prior_turnover=prior_attributes.Va.where(prior_attributes.close.notna()),
        announcement_bucket=category, baseline_date=pre_date, first_session=dates(first_ix),
        daily_entry_date=dates(open_ix), next_open_date=dates(next_ix),
        data_quality_flag=np.select(
            [timing.isna(), events.repeat_period, events.same_day_multiple, ~eligible],
            ["unknown_time", "repeat_period", "multiple_statements", "outside_or_unmatched_universe"],
            default="ok",
        ),
    )
    if not (events.attributes_date.dropna() < events.announcement_date.loc[events.attributes_date.notna()]).all():
        raise ValueError("Security attributes are not pre-event")
    prior_idx = sessions.searchsorted(events.prior_forecast_eps_date, side="right") - 1
    prior = lookup(prices, dates(prior_idx), code)
    asof = lookup(prices, dates(np.where(on_session, ix, ix - 1)), code)
    same_units = prior.factor_level.eq(asof.factor_level) & prior.factor_errors.eq(asof.factor_errors)
    events.loc[~same_units, "company_surprise_eps"] = np.nan
    mkt = topix.set_index("Date", verify_integrity=True)

    def market_at(column, days):
        return mkt[column].reindex(days).reset_index(drop=True)

    events["prior_market_return"] = market_at("C", attribute_date) / market_at("C", dates(ix - 2)) - 1
    next_open = lookup(prices, dates(next_ix), code)
    results = []
    for horizon in ("next_open", *HORIZONS):
        target_ix = next_ix if horizon == "next_open" else first_ix + horizon - 1
        target_date = dates(target_ix)
        end = lookup(prices, target_date, code)
        price = "open" if horizon == "next_open" else "close"
        index_price = "O" if price == "open" else "C"
        total = (end[price] / pre.close - 1).where(end.factor_errors.eq(pre.factor_errors))
        after_entry = (target_ix > open_ix) if horizon == "next_open" else (target_ix >= open_ix)
        post = (end[price] / entry.open - 1).where(
            after_entry & end.factor_errors.eq(entry.factor_errors)
        )
        total_market = market_at(index_price, target_date) / market_at("C", pre_date) - 1
        post_market = market_at(index_price, target_date) / market_at("O", dates(open_ix)) - 1
        after_gap = (target_ix >= next_ix) & (horizon != "next_open")
        gap_post = (end[price] / next_open.open - 1).where(
            after_gap & end.factor_errors.eq(next_open.factor_errors)
        )
        gap_market = market_at(index_price, target_date) / market_at("O", dates(next_ix)) - 1
        results.append(pd.DataFrame({
            "event_id": events.event_id, "horizon": str(horizon), "target_date": target_date,
            "total": total, "post": post, "total_excess": total - total_market,
            "post_excess": post - post_market, "entry_limit_flag": entry.limit_flag,
            "after_gap": gap_post, "after_gap_excess": gap_post - gap_market,
            "target_limit_flag": end.limit_flag, "target_bad_ohlc": end.bad_ohlc,
            "target_missing_bar": end.Vo.isna(), "target_no_trade": end.Vo.eq(0),
        }))
    return events, pd.concat(results, ignore_index=True)
