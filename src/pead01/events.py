"""Build one immutable event per financial statement disclosure."""
from collections import defaultdict
from itertools import groupby
from operator import attrgetter

import numpy as np
import pandas as pd

METRICS = ("EPS", "OP")
FIN_COLUMNS = [
    "DiscDate", "DiscTime", "Code", "DiscNo", "DocType", "CurPerType", "CurPerSt",
    "CurPerEn", "CurFYEn", "NxtFYEn", "Sales", "OP", "EPS", "FOP", "FEPS",
    "FOP2Q", "FEPS2Q", "NxFOP", "NxFEPS", "NxFOP2Q", "NxFEPS2Q",
    "FNCOP", "FNCEPS", "FNCOP2Q", "FNCEPS2Q", "NxFNCOP", "NxFNCEPS", "NxFNCOP2Q", "NxFNCEPS2Q",
]


def build_events(fin):
    fin = fin[FIN_COLUMNS].drop_duplicates().copy()
    if fin.duplicated(["Code", "DiscNo"]).any() or fin.DiscNo.isna().any():
        raise ValueError("Missing or conflicting disclosure identifier")
    fin["DiscDate"] = pd.to_datetime(fin.DiscDate, format="%Y-%m-%d")
    timestamp = fin.DiscTime.str.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d(?::00)?", na=False)
    fin["announcement_datetime"] = (
        fin.DiscDate + pd.to_timedelta(fin.DiscTime.where(timestamp).str.slice(0, 5) + ":00")
    ).dt.tz_localize("Asia/Tokyo")
    for column in FIN_COLUMNS[10:]:
        fin[column] = pd.to_numeric(fin[column], errors="coerce")
    for column in ("CurPerSt", "CurPerEn"):
        fin[f"prior_{column}"] = (pd.to_datetime(fin[column], errors="coerce")
                                   - pd.DateOffset(years=1)).dt.strftime("%Y-%m-%d")

    is_statement = fin.DocType.str.contains("FinancialStatements_", na=False)
    statements = fin[is_statement]
    counts = statements.groupby(["Code", "DiscDate"]).size().to_dict()
    period_counts = statements.groupby(
        ["Code", "DiscDate", "DocType", "CurPerSt", "CurPerEn"]
    ).size().to_dict()
    actuals, forecasts, seen = {}, defaultdict(dict), set()
    rows = []
    ordered = fin.sort_values(
        ["Code", "DiscDate", "announcement_datetime", "DiscNo"]
    )
    for (code, day), disclosures in groupby(ordered.itertuples(index=False), attrgetter("Code", "DiscDate")):
        pending_actuals, pending_forecasts = defaultdict(list), defaultdict(list)
        for row in disclosures:
            if pd.isna(row.DocType):
                continue
            statement = "FinancialStatements_" in row.DocType
            if not statement and row.DocType != "EarnForecastRevision":
                continue
            basis = row.DocType.split("FinancialStatements_")[-1] if statement else None
            scope = basis.split("_")[0] if statement else "Consolidated"
            period_key = (code, row.CurPerSt, row.CurPerEn, row.CurPerType, basis)
            if statement:
                event = {
                    "event_id": "jq:" + code + ":" + row.DiscNo, "security_code": code,
                    "announcement_date": day, "announcement_datetime": row.announcement_datetime,
                    "fiscal_period": row.CurPerEn, "fiscal_start": row.CurPerSt,
                    "earnings_type": row.CurPerType, "document_type": row.DocType,
                    "actual_sales": row.Sales, "actual_eps": row.EPS,
                    "actual_operating_profit": row.OP, "forecast_eps": row.NxFEPS if row.CurPerType == "FY" else row.FEPS,
                    "forecast_operating_profit": row.NxFOP if row.CurPerType == "FY" else row.FOP,
                    "forecast_target": row.NxtFYEn if row.CurPerType == "FY" else row.CurFYEn,
                    "data_source": "J-Quants v2 /fins/summary",
                    "repeat_period": period_key in seen or (
                        period_counts.get((code, day, row.DocType, row.CurPerSt, row.CurPerEn), 0) > 1
                    ),
                    "same_day_multiple": counts[code, day] > 1,
                }
                if pd.notna(row.prior_CurPerSt) and pd.notna(row.prior_CurPerEn):
                    previous = (code, row.prior_CurPerSt, row.prior_CurPerEn,
                                row.CurPerType, basis)
                    event["prior_actual_date"], event["prior_actual_op"] = actuals.get(previous, (pd.NaT, np.nan))
                    pending_actuals[period_key].append((day, row.OP))
                target_end = row.CurPerEn if row.CurPerType == "FY" else row.CurFYEn
                target = (code, target_end, row.CurPerType, scope)
                new_target = (code, event["forecast_target"], "FY", scope)
                for metric, suffix in zip(METRICS, ("eps", "op")):
                    prior_date, prior = forecasts.get(target, {}).get(metric, (pd.NaT, np.nan))
                    event[f"prior_forecast_{suffix}"] = prior
                    event[f"prior_forecast_{suffix}_date"] = prior_date
                    event[f"company_surprise_{suffix}"] = difference(getattr(row, metric), prior)
                revision_date, revision_prior = forecasts.get(new_target, {}).get("OP", (pd.NaT, np.nan))
                event["revision_prior_date"] = revision_date
                event["forecast_revision"] = difference(event["forecast_operating_profit"], revision_prior)
                rows.append(event)
                seen.add(period_key)

            for target, kind, prefix, suffix in [
                (row.CurFYEn, "FY", "F", ""), (row.NxtFYEn, "FY", "NxF", ""),
                (row.CurFYEn, "2Q", "F", "2Q"), (row.NxtFYEn, "2Q", "NxF", "2Q"),
            ]:
                # A half-year target is resolved against the fiscal year at observation time.
                if pd.notna(target):
                    for metric in METRICS:
                        value = getattr(row, prefix + metric + suffix)
                        if pd.notna(value):
                            pending_forecasts[(code, target, kind, scope), metric].append(value)
                        standalone = getattr(row, prefix + "NC" + metric + suffix)
                        if scope == "Consolidated" and pd.notna(standalone):
                            pending_forecasts[(code, target, kind, "NonConsolidated"), metric].append(standalone)
        for key, candidates in pending_actuals.items():
            actuals[key] = candidates[0] if len(candidates) == 1 else (day, np.nan)
        for (key, metric), candidates in pending_forecasts.items():
            forecasts[key][metric] = (day, candidates[0] if len(set(candidates)) == 1 else np.nan)

    events = pd.DataFrame(rows)
    for column in ["prior_actual_date", "prior_actual_op"]:
        if column not in events:
            events[column] = pd.NaT if column.endswith("date") else np.nan
    events["op_yoy"] = events.actual_operating_profit - events.prior_actual_op
    # Audit strictly earlier information dates for all populated prior features.
    for column in ["prior_actual_date", "prior_forecast_eps_date", "prior_forecast_op_date", "revision_prior_date"]:
        valid = events[column].notna()
        if not (events.loc[valid, column] < events.loc[valid, "announcement_date"]).all():
            raise ValueError(f"Future or simultaneous feature: {column}")
    return events


def difference(actual, prior):
    if pd.isna(actual) or pd.isna(prior):
        return np.nan
    return (actual - prior) / abs(prior) if prior else np.nan
