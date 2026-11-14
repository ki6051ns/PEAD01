# PEAD01 — Phase 1–6.1 research summary

**As of 2026-11-14**  
**Status:** exploratory backtest and historical walk-forward research. Independent OOS and live performance: **not available**.

## Economic hypothesis

Financial results and corporate guidance are not necessarily incorporated into Japanese equity prices instantaneously. An initial price response following an earnings announcement may be followed by delayed drift or partial reversal. The project tests whether conditional entry rules and holding periods can capture that effect after realistic cost and capital constraints.

## Phases and key observations

### Phase 1 — Earnings-event baseline
- Approximately **75,369** baseline earnings events from November 2021 to November 2026.
- Investigated initial response, guidance revisions and post-event returns.
- The full population did not exhibit a uniformly attractive positive drift; conditioning matters.

### Phase 2 — Matched-event comparisons
- Matched by announcement date, industry, capitalization and liquidity.
- Negative first-response group showed roughly **−0.39%** five-day relative return; positive first-response group roughly **+0.21%** under the research definitions.
- Corporate guidance revision alone did not establish a strong independent predictive effect after controls.
- Signal availability and entry timestamps must be kept separate: the initial response is not known at the earlier opening price.

### Phase 3 — Executable daily strategy
- Long, short and long-short variants incorporated subsequent executable entry, transaction costs and portfolio capital limits.
- Recomputed fixed-entry reference (1,221 trading days):

| Hold | Trades | Annual return | Sharpe | Maximum drawdown |
| --- | ---: | ---: | ---: | ---: |
| 3 trading days | 12,062 | −0.45% | −0.02 | −18.60% |
| 10 trading days | 7,147 | 5.66% | 0.61 | −18.50% |
| 20 trading days | 5,238 | 6.16% | 0.62 | −17.70% |

These are total-capital return estimates, not market-neutral alpha. Market beta and exposure differences require separate analysis.

### Phase 4 — Intraday price formation
- Expanded minute observations and examined 5–120-minute windows.
- Short-horizon continuation was present in selected samples but later entry materially reduced the edge.
- Earnings-information features did not yield robust positive out-of-sample R-squared for minute-level continuation.

### Phase 5 — Conditional and intraday strategies
- Liquid TOPIX-universe positive initial-response intraday variant: **3,497 trades** over **494** trading days.
- Recomputed reference: **0.82% annual return**, Sharpe **0.65**, maximum drawdown **−0.73%**.
- Entry delay and higher transaction costs reduced or erased profitability.
- Conditional industry/size/regime findings did not provide a robust broad-based selection rule after multiple-test controls.

### Phase 6 — High-dimensional parameter search and ensembles
- **14,909** first-pass candidates.
- First-pass maximum Sharpe **1.55**; constrained reevaluation of top **20** candidates maximum **1.56**.
- Historical selected-WF comparison (all previously researched dates):

| Method | IS Sharpe | WF Sharpe | WF annual return | WF MDD | WF average utilization | WF fills |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Fixed | 0.62 | 0.80 | 7.10% | −8.41% | 56.15% | 1,146 |
| Single | 1.56 | 2.07 | 1.93% | −0.48% | 2.09% | 58 |
| Top-10 | 1.78 | 0.55 | 0.90% | −1.47% | 8.45% | 1,758 |
| Neighbor | 1.54 | 1.95 | 1.39% | −0.26% | 1.59% | 63 |
| Covariance shrinkage | 2.07 | 1.24 | 0.58% | −0.23% | 1.49% | 1,296 |
| Dynamic monthly / 252d | — | 1.68 | 0.61% | −0.20% | 2.27% | 2,857 |

**Finding:** high Sharpe can coexist with economically small absolute return and sparse positions. A naive Top-K ensemble did not robustly improve results.

### Phase 6.1 — Sizing, leverage and financing
- **903 cases** finished successfully; local implementation reported committed as `20e7a27`.
- Standard-cost, training-period-selected historical WF:

| Method | WF Sharpe | Annual return | MDD | Mean utilization | Fills |
| --- | ---: | ---: | ---: | ---: | ---: |
| Single | **2.02** | 1.88% | −0.49% | 2.10% | 58 |
| Neighbor | 1.91 | 1.35% | −0.26% | 1.60% | 63 |
| Dynamic monthly / 252d | 1.60 | 0.62% | −0.20% | 2.21% | 2,857 |
| Composite, shrinkage | 1.58 | **2.28%** | −0.71% | 2.63% | 2,895 |
| Composite, equal | 1.57 | 2.06% | −0.65% | 2.49% | 2,895 |

**Retrospectively inspected fixed-grid scenarios (not selection-valid WF):**

| Configuration | Sharpe | Annual return | MDD | Mean utilization |
| --- | ---: | ---: | ---: | ---: |
| Composite equal, 10× size / 5% utilization target | 2.42 | 4.94% | −0.99% | 10.55% |
| Composite shrinkage, 10× size / 5% target | 2.42 | 5.18% | −0.99% | 10.72% |
| Composite equal, 10× size / 10% target | 2.15 | 6.54% | −1.23% | 11.98% |

These fixed-grid estimates span **334 trading days**. They reflect retrospective configuration inspection and must not be promoted as independent OOS results.

Some configurations displayed identical results for nominal leverage caps from 1× to 3×, suggesting the caps were nonbinding in those instances or warranting an implementation audit. Position sizing, rather than credit leverage itself, appears to explain much of the performance increase in those examples.

## Interpretation

**Established research outcomes:**
- Post-earnings initial price reaction relates to conditional subsequent price paths in the studied sample.
- A straightforward 20-day long rule achieved only **Sharpe 0.62**.
- Selection and ensembles produced historical WF Sharpe around **1.6–2.0** for some configurations, often at very low invested-capital utilization.
- Larger fixed-grid sizing produced promising historical return/Sharpe tradeoffs that require selection-valid follow-up.

**Not established:**
- Independence from previous researcher choices or a truly untouched OOS sample.
- Executability at reported prices and volumes, including borrowing availability, margin rules and market impact.
- Performance stability under larger real orders and financing costs.
- Live realized alpha.

## Priority next steps

1. Inspect retained trade-level and position-level records and verify nonbinding margin-cap cases.
2. Audit concrete Japanese margin rules and broker-specific borrowing/maintenance requirements.
3. Re-evaluate sizing and market-impact capacity without expanding the original 14,909-signal search.
4. Freeze selection rules, then test on newly acquired **untouched** data and/or forward paper trading.
5. Publish compact reproducible summaries, not licensed raw data or confidential records.

## Research operations and token efficiency

- Use a local Python batch runner for grid search, ensembles and walk-forward experiments.
- Preserve Parquet artifacts and resumable checkpoints locally.
- Limit Codex to implementation, isolated tests, code review and concise result interpretation.
- Do not stream large CSV/Parquet extracts or verbose logs into model context.
- Respect the operator's rolling five-hour usage budget: at or below 25% remaining, avoid launching large Codex tasks; around 10%, checkpoint and stop. This requires operator verification rather than assuming a guaranteed usage API.
- Preserve exact distinctions among IS, historical WF, retrospective fixed-grid evaluation and independent OOS.

## Publication boundaries

The report documents research, not live performance, and is not a promise of future results. Validate software-license and market-data redistribution terms, ensure all private tokens/paths are removed, and review the commit history before making local source history publicly available.
