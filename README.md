# PEAD01

**Post-Earnings Announcement Drift Research for Japanese Equities**

日本株の決算発表後の価格形成を対象に、経済的仮説に基づく売買ルール、パラメータ最適化、アンサンブル、資金配分と信用コストを研究するプロジェクトです。

## Research status (2026-11-14)

**Phase 1–6.1 completed as exploratory research.** Results below are historical simulations, **not live trading performance**. The tested walk-forward (WF) periods overlap periods previously inspected during research; they are **not independent, untouched out-of-sample (OOS) evidence**.

| Stage | Main result |
| --- | --- |
| Phase 1–2 | Approximately 75,369 earnings events; initial price response and subsequent relative returns were examined |
| Phase 3 | Simple 20-trading-day long: annual return **6.16%**, Sharpe **0.62**, maximum drawdown **−17.70%** (1,221 trading days) |
| Phase 4–5 | Intraday price response and execution-delay sensitivity examined; short-horizon opportunities were small and cost sensitive |
| Phase 6 | 14,909 preliminary candidates; 20 constrained re-evaluations; best selected single-strategy WF Sharpe **2.07**, annual return **1.93%** |
| Phase 6.1 | 903 sizing / leverage cases completed; selected single-strategy cost-adjusted WF Sharpe **2.02**, annual return **1.88%**; selected shrinkage composite WF Sharpe **1.58**, annual return **2.28%** |

The high-Sharpe candidates were characterized by **very low capital utilization** (approximately 1.6–2.6% on the selected WF results). Some **retrospectively evaluated fixed-grid** sizing cases achieved Sharpe above 2 and annual return above 5%, but these **must not be presented as selection-valid WF or independent OOS results**.

## Research methodology

1. **Economic rationale** — delayed incorporation of post-earnings information into prices, momentum and reversal.
2. **Executable strategy rules** — entry timestamp, holding horizon, liquidity and event filters, with conservative transaction costs.
3. **Parameter exploration** — candidate-grid screening, neighboring-parameter ensembles, Top-K, covariance-shrinkage, dynamic allocation.
4. **Capital and risk constraints** — portfolio-level cash usage, position sizing, margin financing, turnover and drawdown.
5. **Validation** — chronological walk-forward tests, explicit selection-bias disclosures and future untouched OOS testing.

See [research/phase1_to_phase61_summary.md](research/phase1_to_phase61_summary.md) for results and limitations.

## Reproducibility and disclosure

- Avoid using information before it was publicly and operationally available.
- Distinguish **in-sample (IS)**, **historical walk-forward (WF)**, **retrospectively selected fixed-grid**, **independent OOS**, and **live** results.
- Report capital utilization, transaction counts, costs, and drawdowns alongside Sharpe ratios.
- No brokerage credentials, private research datasets, personally identifiable information, or company-confidential material should be committed.
- Raw J-Quants or other licensed data should not be redistributed without permission.

## Code status

The full local Codex implementation, including the reported local commit `20e7a27`, **has not yet been synchronized to this GitHub repository**. This initial public repository contains documentation only. Do not interpret the published text as independently reproduced source-code results.

The next steps are a careful local-file review and Git push of publishable code, followed by execution-capacity testing and independent OOS validation.

## Scope

Research and simulation only. Not investment advice or evidence of realized investment returns.
