# 決算情報と初動の組み合わせ

## 60分後の追加超過と営業利益予想修正

| info | initial | n | mean | median | lo | hi |
| --- | --- | --- | --- | --- | --- | --- |
| flat | negative | 3810 | 0.02% | -0.03% | -0.07% | 0.11% |
| flat | positive | 2557 | 0.06% | 0.01% | -0.05% | 0.17% |
| negative | negative | 540 | 0.04% | 0.02% | -0.17% | 0.26% |
| negative | positive | 109 | 0.38% | 0.29% | -0.10% | 0.86% |
| positive | negative | 510 | -0.09% | -0.05% | -0.34% | 0.15% |
| positive | positive | 1172 | 0.02% | 0.01% | -0.14% | 0.18% |
| unknown | negative | 2531 | -0.13% | -0.18% | -0.25% | -0.02% |
| unknown | positive | 1947 | 0.24% | 0.20% | 0.08% | 0.40% |

## 会社予想差・前年同期間差

| feature | info | initial | n | mean | median | lo | hi |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OP_company差 | negative | negative | 810 | -0.21% | -0.25% | -0.40% | -0.03% |
| OP_company差 | negative | positive | 421 | 0.01% | 0.14% | -0.27% | 0.29% |
| OP_company差 | positive | negative | 1543 | -0.13% | -0.15% | -0.25% | 0.00% |
| OP_company差 | positive | positive | 1413 | 0.24% | 0.18% | 0.07% | 0.42% |
| OP_series差 | negative | negative | 2691 | -0.03% | -0.05% | -0.13% | 0.06% |
| OP_series差 | negative | positive | 1168 | 0.19% | 0.14% | 0.01% | 0.38% |
| OP_series差 | positive | negative | 4009 | -0.06% | -0.10% | -0.15% | 0.04% |
| OP_series差 | positive | positive | 4055 | 0.12% | 0.06% | 0.02% | 0.21% |
| EPS_company差 | negative | negative | 774 | -0.25% | -0.29% | -0.42% | -0.08% |
| EPS_company差 | negative | positive | 407 | -0.01% | -0.04% | -0.36% | 0.34% |
| EPS_company差 | positive | negative | 1617 | -0.12% | -0.14% | -0.26% | 0.01% |
| EPS_company差 | positive | positive | 1497 | 0.27% | 0.23% | 0.12% | 0.42% |

## 同じ5分時点・同じ集合で60分までを予測

| 予測対象 | 年 | モデル | 学習 | 評価 | RMSE | OOS R² | 符号正解率 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| continuation | 2025 | information | 832 | 3881 | 2.54% | -0.0516 | 50.45% |
| continuation | 2025 | price | 832 | 3881 | 2.54% | -0.0540 | 50.91% |
| continuation | 2025 | combined | 832 | 3881 | 2.54% | -0.0533 | 51.17% |
| continuation | 2026 | information | 4713 | 3649 | 2.52% | -0.0040 | 51.11% |
| continuation | 2026 | price | 4713 | 3649 | 2.52% | -0.0052 | 50.97% |
| continuation | 2026 | combined | 4713 | 3649 | 2.52% | -0.0042 | 50.62% |
| initial | 2025 | information | 1474 | 6716 | 6.00% | 0.0663 | 59.53% |
| initial | 2025 | pre_event_controls | 1474 | 6716 | 6.25% | -0.0138 | 53.90% |
| initial | 2026 | information | 8185 | 6018 | 6.07% | 0.0658 | 63.36% |
| initial | 2026 | pre_event_controls | 8185 | 6018 | 6.30% | -0.0043 | 55.73% |

3モデルは同じ対象と業種・規模・流動性の調整を使用。財務情報モデルはTDnet開示時点で取得できたと仮定した理論比較。実際のJ-Quants配信時刻は確認できない。continuationは5分から60分、initialは発表前から5分。initialでは5分時点の価格を説明変数に入れず、事前属性のみのモデルと比較した。
