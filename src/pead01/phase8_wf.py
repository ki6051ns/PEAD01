"""Common walk-forward folds and Phase 8 selection using only matured labels."""
from itertools import product

import numpy as np
import pandas as pd

from .phase6_daily_wf import features, sharpe
from .phase6_report import weights

PARAMETERS = ["method", "entry", "hold", "exit_price", "direction", "threshold"]
HISTORY = ["start", "end", "blank", "mode", "id", "weight"]


def schedules(n, cfg):
    earliest = cfg["min_training_days"] + max(cfg["validation_days"]) + 2 * max(cfg["blanks"])
    first = max(earliest, n-cfg["wf_sessions"])
    if first >= n:
        raise ValueError("No WF sessions after minimum training, validation and two blanks")
    for offset in cfg["update_offsets"]:
        bounds = [first, *range(first + (offset or cfg["update_days"]), n, cfg["update_days"]), n]
        yield offset, list(zip(bounds, bounds[1:]))


def windows(start, blank, days, design, max_days):
    validation_end = start - blank
    train_end = validation_end
    if design == "B" or days:
        train_end -= (max_days if design == "B" else days) + blank
    return (0, train_end), (validation_end-days, validation_end) if days else None


def conditions(cfg):
    for design, days in product(("A", "B"), cfg["validation_days"]):
        for rule in ("rerank", "screen") if days else ("direct",):
            yield design, days, rule


def intervals(folds, cfg):
    result = set(folds)
    for (start, _), blank, (design, days, _) in product(folds, cfg["blanks"], conditions(cfg)):
        result.update(window for window in windows(start, blank, days, design, max(cfg["validation_days"]))
                      if window is not None)
    return sorted(result)


def score_paths(trades, cfg, sessions, ranges, first_id):
    """Score the Phase 6 candidate streams with strictly completed trade paths."""
    catalogue, audit, streams = [], [], {}
    for (method, entry, hold, exit_price), paths in trades.groupby(PARAMETERS[:4], sort=True):
        paths = paths.sort_values("start", kind="stable").reset_index(drop=True)
        day, parent, delta, fee, borrow, exposure = features(paths, cfg, sessions)
        start = paths.start.to_numpy(int)
        signal = sessions.searchsorted(paths.signal_time.dt.normalize())
        end = np.where(paths.closed, paths.end, len(sessions))
        gap = paths.gap.to_numpy()
        boundaries = np.r_[0, np.cumsum([len(m) for m in paths.marks])]
        loanable = paths.loanable.to_numpy(bool)
        slices = [(lo, hi, *start.searchsorted([lo, hi])) for lo, hi in ranges]
        # Expanding windows share a left boundary. Add each newly matured path
        # only once, then derive each score from the cumulative daily buckets.
        maturity_order = np.argsort(end[parent], kind="stable")
        ordered_parent = parent[maturity_order]
        maturity = end[ordered_parent]
        training_cutoffs = sorted(hi for lo, hi in ranges if lo == 0)
        for direction, threshold in product(cfg["directions"], cfg["thresholds"]):
            c = first_id + len(catalogue)
            catalogue.append((c, method, entry, hold, exit_price, direction, threshold))
            side = np.sign(gap)
            if direction == "long":
                side = side.clip(min=0)
            elif direction == "short":
                side = side.clip(max=0)
            mask = (side != 0) & (np.abs(gap) >= threshold) & ((side > 0) | loanable)
            net = delta * side[parent] - fee - borrow * (side[parent] < 0)
            mature_mask = mask[ordered_parent] & (signal[ordered_parent] >= 0)
            realized = maturity_order[mature_mask]
            cutoffs = maturity[mature_mask].searchsorted(training_cutoffs)
            total_pnl = np.zeros(len(sessions))
            total_gross = np.zeros(len(sessions))
            prior = 0
            expanded = {}
            for hi, cutoff in zip(training_cutoffs, cutoffs):
                rows = realized[prior:cutoff]
                total_pnl += np.bincount(day[rows], net[rows], minlength=len(sessions))
                total_gross += np.bincount(day[rows], exposure[rows], minlength=len(sessions))
                expanded[hi] = total_pnl[:hi] / np.maximum(total_gross[:hi], 1)
                prior = cutoff
            for lo, hi, left, right in slices:
                section = slice(left, right)
                available = mask[section] & (signal[section] >= lo)
                valid = available & (end[section] < hi)
                if lo == 0:
                    series = expanded[hi]
                else:
                    marks = slice(boundaries[left], boundaries[right])
                    keep = valid[parent[marks]-left]
                    days = day[marks][keep] - lo
                    pnl = np.bincount(days, net[marks][keep], minlength=hi-lo)
                    gross = np.bincount(days, exposure[marks][keep], minlength=hi-lo)
                    series = pnl / np.maximum(gross, 1)
                streams[c, lo, hi] = series.astype("float32")
                audit.append((c, lo, hi, int(valid.sum()), int((available & ~valid).sum()),
                              int(end[section][valid].max()) if valid.any() else -1,
                              sharpe(series), float(np.prod(1 + series)-1)))
    return (pd.DataFrame(catalogue, columns=["id", *PARAMETERS]),
            pd.DataFrame(audit, columns=["id", "lo", "hi", "fills", "purged", "last_label", "sharpe", "return"]),
            streams)


def choose(train, validation, rule, cfg):
    valid = train.loc[train.fills.ge(cfg["min_train_fills"])].dropna(subset=["sharpe"])
    shortlist = valid.sort_values("sharpe", ascending=False, kind="stable").head(50).index
    if validation is None:
        return shortlist, shortlist
    screened = validation.loc[shortlist]
    screened = screened.loc[screened.fills.ge(cfg["min_validation_fills"])].dropna(subset=["sharpe"])
    if rule == "rerank":
        screened = screened.sort_values("sharpe", ascending=False, kind="stable")
    return shortlist, screened.index


def select(catalogue, scores, streams, folds, cfg, design, days, rule):
    entries, diagnostics = [], []
    candidates = catalogue.set_index("id")
    for start, end in folds:
        singles = []
        def add(blank, mode, ids, allocation):
            if not len(ids):
                entries.append((start, end, blank, mode, -1, 0.))
            for candidate, weight in zip(ids, allocation):
                entries.append((start, end, blank, mode, candidate, float(weight)))
        for b in cfg["blanks"]:
            tr, va = windows(start, b, days, design, max(cfg["validation_days"]))
            train, forward = scores[tr], scores[start, end]
            validation = scores[va] if va else None
            shortlist, best = choose(train, validation, rule, cfg)
            diagnostic = train.loc[shortlist, ["sharpe", "fills", "purged", "last_label"]].add_prefix("train_")
            if validation is not None:
                diagnostic = diagnostic.join(validation[["sharpe", "fills", "purged", "last_label"]].add_prefix("validation_"))
            diagnostic = diagnostic.join(forward[["return", "fills"]].add_prefix("forward_"))
            diagnostics.append(diagnostic.reset_index().assign(start=start, end=end, blank=b, train_end=tr[1],
                val_start=va[0] if va else -1, val_end=va[1] if va else -1,
                train_rank=np.arange(1, len(shortlist)+1), passed=shortlist.isin(best)))
            top = best[:cfg["top_k"]]
            if len(best):
                winner = best[0]
                near = candidates.loc[best].ne(candidates.loc[winner]).sum(axis=1).le(1)
                neighbors = best[near.to_numpy()]
                shrink = weights(np.array([streams[(c, *tr)] for c in top]), "shrink")
                singles.append((b, winner, tr))
            else:
                neighbors, shrink = [], []
            add(b, f"single_b{b}", best[:1], [1.])
            add(b, f"neighbor_b{b}", neighbors, np.full(len(neighbors), 1/max(1, len(neighbors))))
            add(b, f"shrink_b{b}", top, shrink)

        if not singles:
            for method in ("equal", "shrink", "dynamic"):
                add(-1, f"blank_{method}", [], [])
            continue
        lo = max(tr[0] for _, _, tr in singles)
        hi = min(tr[1] for _, _, tr in singles)
        aligned = np.array([streams[(c, *tr)][lo-tr[0]:hi-tr[0]] for _, c, tr in singles])
        dynamic = np.exp(np.clip(np.nan_to_num([sharpe(s[-63:]) for s in aligned]), -3, 3))
        allocations = {"equal": np.full(len(singles), 1/len(singles)), "shrink": weights(aligned, "shrink"),
                       "dynamic": dynamic/dynamic.sum()}
        for method, allocation in allocations.items():
            for (b, c, _), weight in zip(singles, allocation):
                add(b, f"blank_{method}", [c], [weight])
    return pd.DataFrame(entries, columns=HISTORY), pd.concat(diagnostics, ignore_index=True)

