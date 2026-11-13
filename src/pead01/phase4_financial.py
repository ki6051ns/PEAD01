"""Financial comparisons using only earlier disclosure dates."""
from collections import defaultdict
from itertools import groupby
from operator import attrgetter

import numpy as np
import pandas as pd

METRICS = ("Sales", "OP", "OdP", "EPS")
FORECAST = ("", "2Q")
COLUMNS = ["Code", "DiscDate", "DiscTime", "DiscNo", "DocType", "CurPerType",
           "CurPerSt", "CurPerEn", "CurFYSt", "CurFYEn", "NxtFYEn", "FDivAnn", "NxFDivAnn"]
COLUMNS += list(METRICS) + [f"{prefix}{scope}{metric}{period}"
                            for prefix in ("F", "NxF") for scope in ("", "NC")
                            for metric in METRICS for period in FORECAST]
FLOORS = {"Sales": 1e6, "OP": 1e6, "OdP": 1e6, "EPS": 1., "dividend": 1.}


def ratio(current, old, floor):
    return (current - old) / abs(old) if pd.notna(current) and pd.notna(old) and abs(old) >= floor else np.nan


def sign_change(current, previous):
    if pd.isna(current) or pd.isna(previous):
        return None
    if current > 0 and previous <= 0:
        return "to_profit"
    if current < 0 and previous >= 0:
        return "to_loss"
    return "no_cross"


def financial_features(fin, events):
    fin = fin.drop_duplicates().copy()
    for column in COLUMNS[11:]:
        fin[column] = pd.to_numeric(fin[column], errors="coerce")
    for column in ("CurPerSt", "CurPerEn"):
        dates = pd.to_datetime(fin[column], errors="coerce")
        # Keep fiscal month ends aligned across leap years.
        prior = dates - pd.DateOffset(years=1)
        prior = prior.where(~dates.dt.is_month_end, prior + pd.offsets.MonthEnd(0))
        fin["prior_" + column] = prior.dt.strftime("%Y-%m-%d")
    wanted = set(events.event_id)
    rows = []
    ordered = fin.sort_values(["Code", "DiscDate", "DiscTime", "DiscNo"])
    for code, disclosures in groupby(ordered.itertuples(index=False), attrgetter("Code")):
        latest, actuals = {}, {}
        for day, day_rows in groupby(disclosures, attrgetter("DiscDate")):
            same_day = list(day_rows)
            updates, new_actuals = defaultdict(list), defaultdict(list)
            for r in same_day:
                document = r.DocType if isinstance(r.DocType, str) else ""
                statement = "FinancialStatements_" in document
                if not statement and document not in ("EarnForecastRevision", "DividendForecastRevision"):
                    continue
                basis = document.split("FinancialStatements_")[-1] if statement else None
                scope = basis.split("_")[0] if statement else "Consolidated"
                key = (r.CurPerSt, r.CurPerEn, r.CurPerType, basis)
                event_id = f"jq:{code}:{r.DiscNo}"
                current = {m: getattr(r, m) for m in METRICS}
                prior_key = (r.prior_CurPerSt, r.prior_CurPerEn, r.CurPerType, basis)
                prior = actuals.get(prior_key, {})
                if event_id in wanted:
                    out = {"event_id": event_id, "same_minute_structured_count":
                           sum(other.DiscTime == r.DiscTime for other in same_day) - 1,
                           "prior_actual_source": prior.get("date"),
                           "prior_actual_period": prior.get("period"),
                           "current_period": r.CurPerEn, "forecast_scope": scope}
                    forward = r.CurPerType == "FY"
                    target = r.NxtFYEn if forward else r.CurFYEn
                    out["revision_target"] = target
                    for m in METRICS:
                        value = current[m]
                        lag = prior.get(m, np.nan)
                        target_key = (scope, target, "", m)
                        revised = getattr(r, ("NxF" if forward else "F") + m)
                        revision_date, old = latest.get(target_key, (None, np.nan))
                        old_state = revision_date is not None
                        fiscal_target = r.CurPerEn if forward else r.CurFYEn
                        expected = latest.get((scope, fiscal_target, "2Q" if r.CurPerType == "2Q" else "", m),
                                              (None, np.nan)) if r.CurPerType in ("FY", "2Q") else (None, np.nan)
                        out.update({
                            f"{m}_actual": value, f"{m}_prior": lag, f"{m}_yoy": ratio(value, lag, FLOORS[m]),
                            f"{m}_series_expectation": lag, f"{m}_series差": value - lag,
                            f"{m}_series_surprise": ratio(value, lag, FLOORS[m]),
                            f"{m}_company差": value - expected[1],
                            f"{m}_company_surprise": ratio(value, expected[1], FLOORS[m]),
                            f"{m}_company_date": expected[0], f"{m}_revision_date": revision_date,
                            f"{m}_revision_before": old, f"{m}_revision_after": revised,
                            f"{m}_revision_amount": revised - old,
                            f"{m}_revision_rate": ratio(revised, old, FLOORS[m]),
                            f"{m}_revision_cross": sign_change(revised, old),
                            f"{m}_actual_cross": sign_change(value, lag),
                            f"{m}_revision_status": ("comparable" if pd.notna(revised) and pd.notna(old)
                                                     else "prior_record_missing_value" if pd.notna(revised) and old_state
                                                     else "left_censored_or_new" if pd.notna(revised)
                                                     else "current_missing"),
                        })
                    dividend = r.NxFDivAnn if forward else r.FDivAnn
                    prev_div = latest.get((scope, target, "", "dividend"), (None, np.nan))[1]
                    out["dividend_revision"] = ratio(dividend, prev_div, FLOORS["dividend"])
                    out["margin"] = r.OP / r.Sales if r.Sales > 0 else np.nan
                    out["margin_change"] = out["margin"] - prior.get("margin", np.nan)
                    current_forecast = latest.get((scope, r.CurFYEn, "", "OP"), (None, np.nan))[1]
                    out["op_progress"] = r.OP / current_forecast if current_forecast >= FLOORS["OP"] else np.nan
                    out["op_progress_change"] = out["op_progress"] - prior.get("progress", np.nan)
                    rows.append(out)
                if statement:
                    prior_year_forecast = latest.get((scope, r.CurFYEn, "", "OP"), (None, np.nan))[1]
                    current["margin"] = r.OP / r.Sales if r.Sales > 0 else np.nan
                    current["progress"] = r.OP / prior_year_forecast if prior_year_forecast >= FLOORS["OP"] else np.nan
                    new_actuals[key].append({**current, "date": day, "period": r.CurPerEn})
                for target, prefix in [(r.CurFYEn, "F"), (r.NxtFYEn, "NxF")]:
                    if pd.isna(target):
                        continue
                    for m in METRICS:
                        for period in FORECAST:
                            for field_scope, accounting in [("", scope), ("NC", "NonConsolidated")]:
                                value = getattr(r, prefix + field_scope + m + period)
                                if pd.notna(value) or (statement and not field_scope and period == ""):
                                    updates[(accounting, target, period, m)].append(value)
                    value = r.FDivAnn if prefix == "F" else r.NxFDivAnn
                    if pd.notna(value):
                        updates[(scope, target, "", "dividend")].append(value)
            for key, values in updates.items():
                known = {v for v in values if pd.notna(v)}
                latest[key] = (day, next(iter(known)) if len(known) == 1 else np.nan)
            for key, values in new_actuals.items():
                actuals[key] = values[0] if len(values) == 1 else {}
    result = pd.DataFrame(rows)
    dates = events.set_index("event_id").announcement_date.reindex(result.event_id).reset_index(drop=True)
    for field in ["prior_actual_source", *[f"{m}_{kind}_date" for m in METRICS for kind in ("company", "revision")]]:
        values = pd.to_datetime(result[field])
        if (values.notna() & values.ge(dates)).any():
            raise ValueError(f"Future financial information in {field}")
        result[field] = values
    for missing in ["consensus_surprise", "buyback", "withdrawal", "impairment", "segments", "one_off"]:
        result[missing] = np.nan
    return result
