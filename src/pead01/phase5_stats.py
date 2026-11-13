"""Conditional comparisons and inference for Phase 5."""
import numpy as np
import pandas as pd


def fixed_effects(frame, dimension, outcome):
    fields = ["strength", "initial", "timing", "year", "sector", "size", "liquidity", "regime"]
    fields = list(dict.fromkeys([dimension, *fields]))
    data = frame.dropna(subset=[outcome, *fields]).copy()
    data = data.loc[np.isfinite(data[outcome]) & np.isfinite(data.initial_excess)]
    data["initial_abs"] = data.initial_excess.abs()
    data["size_direction"] = data["size"].astype(str) + "|" + data["initial"]
    fields = [*fields, "size_direction"] if dimension == "size_direction" else fields
    fields = list(dict.fromkeys(fields))
    encoded = pd.get_dummies(data[fields].astype(str), drop_first=True, dtype=float)
    variables = [c for c in encoded if c.startswith(dimension + "_")]
    # Size-direction cells replace redundant size and direction main effects.
    if dimension == "size_direction":
        encoded = encoded.drop(columns=[c for c in encoded if c.startswith(("size_", "initial_"))
                                       and not c.startswith("size_direction_")])
    x = np.column_stack([np.ones(len(data)), data.initial_abs, encoded])
    y = data[outcome].to_numpy()
    b = np.linalg.lstsq(x, y, rcond=None)[0]
    weights = pd.DataFrame(x * (y - x @ b)[:, None])
    date, code = data.announcement_date.to_numpy(), data.security_code.to_numpy()

    def meat(keys):
        grouped = weights.groupby(keys).sum().to_numpy()
        return grouped.T @ grouped * len(grouped) / (len(grouped) - 1) if len(grouped) > 1 else np.full(
            (x.shape[1], x.shape[1]), np.nan)

    inv = np.linalg.pinv(x.T @ x)
    cov = inv @ (meat(date) + meat(code) - meat([date, code])) @ inv
    rows = []
    for term in variables:
        i = encoded.columns.get_loc(term) + 2
        se = np.sqrt(cov[i, i]) if cov[i, i] >= 0 else np.nan
        rows.append((dimension, term, len(data), b[i], b[i] - 1.96*se, b[i] + 1.96*se))
    return pd.DataFrame(rows, columns=["dimension", "term", "n", "estimate", "lo", "hi"])


def blocks(frame, value, seed=5):
    """Moving-block bootstrap of 5 consecutive observed disclosure dates."""
    totals = frame.dropna(subset=[value]).groupby("announcement_date")[value].agg(["sum", "size"])
    n = len(totals)
    if n < 5:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    start = rng.integers(0, n, size=(999, int(np.ceil(n / 5))))
    indices = ((start[:, :, None] + np.arange(5)) % n).reshape(999, -1)[:, :n]
    draws = totals.to_numpy()[indices].sum(axis=1)
    return np.quantile(draws[:, 0] / draws[:, 1], [.025, .975])


def matched_size(frame):
    """Compare above/below ¥100bn within day, sector, liquidity and initial strength."""
    data = frame.dropna(subset=["sector", "liquidity", "strength", "market_cap", "signed"])
    data = data.loc[data.prior_turnover.gt(0)].sort_values("event_id")
    keys = ["announcement_date", "sector", "liquidity", "strength", "initial", "timing"]
    matches = []
    for _, cell in data.groupby(keys, observed=True):
        large = cell.loc[cell.market_cap.ge(1e11)]
        small = cell.loc[cell.market_cap.lt(1e11)]
        if large.empty or small.empty:
            continue
        for row in large.itertuples():
            distances = (np.log(small.prior_turnover / row.prior_turnover)).abs()
            nearest = small.loc[distances.idxmin()]
            matches.append((row.event_id, nearest.event_id, row.announcement_date, row.security_code, row.initial,
                            row.signed - nearest.signed, float(distances.min())))
    return pd.DataFrame(matches, columns=["event_id", "control", "announcement_date", "security_code",
                                          "initial", "difference", "turnover_distance"])
