# 情報との相互作用・費用控除後の試算

| feature | info | initial | n | 銘柄 | mean | lo | hi |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OP_company差 | flat | down | 79 | 74 | 0.58% | -0.04% | 1.20% |
| OP_company差 | negative | down | 553 | 471 | 0.12% | -0.11% | 0.34% |
| OP_company差 | positive | down | 969 | 762 | -0.01% | -0.16% | 0.14% |
| OP_company差 | unknown | down | 3131 | 1617 | -0.03% | -0.15% | 0.09% |
| OP_company差 | flat | up | 57 | 54 | 0.40% | -0.45% | 1.26% |
| OP_company差 | negative | up | 258 | 239 | 0.10% | -0.26% | 0.45% |
| OP_company差 | positive | up | 742 | 573 | 0.21% | -0.04% | 0.46% |
| OP_company差 | unknown | up | 2186 | 1278 | -0.09% | -0.24% | 0.06% |
| OP_revision_amount | flat | down | 2512 | 1403 | -0.06% | -0.17% | 0.05% |
| OP_revision_amount | negative | down | 355 | 305 | -0.08% | -0.37% | 0.20% |
| OP_revision_amount | positive | down | 294 | 248 | 0.14% | -0.19% | 0.47% |
| OP_revision_amount | unknown | down | 1571 | 1125 | 0.09% | -0.07% | 0.24% |
| OP_revision_amount | flat | up | 1520 | 1017 | -0.12% | -0.27% | 0.03% |
| OP_revision_amount | negative | up | 59 | 57 | 0.64% | -0.17% | 1.44% |
| OP_revision_amount | positive | up | 584 | 443 | -0.12% | -0.33% | 0.10% |
| OP_revision_amount | unknown | up | 1080 | 797 | 0.20% | -0.02% | 0.42% |
| op_eps_conflict | False | down | 1245 | 926 | 0.02% | -0.14% | 0.17% |
| op_eps_conflict | True | down | 284 | 271 | 0.38% | 0.11% | 0.64% |
| op_eps_conflict | unknown | down | 3203 | 1630 | -0.04% | -0.16% | 0.08% |
| op_eps_conflict | False | up | 837 | 650 | 0.19% | -0.03% | 0.41% |
| op_eps_conflict | True | up | 177 | 173 | 0.30% | -0.11% | 0.71% |
| op_eps_conflict | unknown | up | 2229 | 1290 | -0.10% | -0.24% | 0.05% |

## 遅延・容量・費用

| 対象 | 遅延分 | 初動 | 候補 | 約定 | 平均ネット | 共通ネット | 元本加重 | 累積損益 | 最大DD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 1 | up | 5612 | 5612 | -0.03% | -0.02% | 0.02% | 1.02% | -2.13% |
| all | 1 | down | 5717 | 5705 | -0.09% | -0.10% | -0.11% | -5.53% | -5.97% |
| all | 5 | up | 5514 | 5514 | -0.02% | -0.02% | 0.01% | 0.25% | -3.02% |
| all | 5 | down | 5636 | 5623 | -0.08% | -0.08% | -0.09% | -4.43% | -5.09% |
| all | 15 | up | 5339 | 5339 | -0.04% | -0.05% | -0.02% | -1.08% | -3.08% |
| all | 15 | down | 5518 | 5508 | -0.08% | -0.09% | -0.09% | -4.55% | -4.78% |
| liquid_topix | 1 | up | 3497 | 3497 | 0.05% | 0.04% | 0.05% | 1.61% | -0.73% |
| liquid_topix | 1 | down | 4251 | 4251 | -0.14% | -0.14% | -0.14% | -5.94% | -6.54% |
| liquid_topix | 5 | up | 3479 | 3479 | 0.03% | 0.03% | 0.03% | 0.91% | -0.99% |
| liquid_topix | 5 | down | 4231 | 4231 | -0.10% | -0.10% | -0.10% | -4.28% | -5.16% |
| liquid_topix | 15 | up | 3438 | 3438 | -0.01% | -0.01% | -0.01% | -0.41% | -1.83% |
| liquid_topix | 15 | down | 4161 | 4161 | -0.10% | -0.10% | -0.10% | -4.03% | -4.19% |
| non_topix | 1 | up | 1594 | 1594 | -0.23% | -0.24% | -0.10% | -0.99% | -2.89% |
| non_topix | 1 | down | 933 | 933 | 0.09% | 0.09% | 0.12% | 0.74% | -0.74% |
| non_topix | 5 | up | 1546 | 1546 | -0.15% | -0.17% | -0.08% | -0.74% | -2.59% |
| non_topix | 5 | down | 896 | 896 | -0.02% | 0.00% | 0.02% | 0.12% | -0.73% |
| non_topix | 15 | up | 1458 | 1458 | -0.14% | -0.17% | -0.07% | -0.63% | -2.16% |
| non_topix | 15 | down | 882 | 882 | -0.02% | -0.03% | -0.04% | -0.23% | -0.70% |
| strong_liquid_topix | 1 | up | 1956 | 1956 | 0.06% | 0.05% | 0.06% | 1.17% | -0.75% |
| strong_liquid_topix | 1 | down | 2369 | 2369 | -0.18% | -0.18% | -0.18% | -4.17% | -4.24% |
| strong_liquid_topix | 5 | up | 1944 | 1944 | 0.04% | 0.04% | 0.04% | 0.87% | -0.79% |
| strong_liquid_topix | 5 | down | 2355 | 2355 | -0.10% | -0.09% | -0.10% | -2.28% | -2.94% |
| strong_liquid_topix | 15 | up | 1931 | 1931 | -0.01% | -0.01% | -0.01% | -0.17% | -1.15% |
| strong_liquid_topix | 15 | down | 2333 | 2333 | -0.09% | -0.09% | -0.09% | -2.15% | -2.16% |

## 固定条件の年別成績と2026年時系列評価

| 対象 | 方向 | 年 | 約定 | 累積損益 |
| --- | --- | --- | --- | --- |
| all | down | 2024 | 482 | -0.30% |
| all | down | 2025 | 2623 | -2.43% |
| all | down | 2026 | 2600 | -2.79% |
| all | up | 2024 | 453 | -0.33% |
| all | up | 2025 | 2751 | 0.78% |
| all | up | 2026 | 2408 | 0.56% |
| liquid_topix | down | 2024 | 348 | -0.19% |
| liquid_topix | down | 2025 | 1868 | -2.18% |
| liquid_topix | down | 2026 | 2035 | -3.58% |
| liquid_topix | up | 2024 | 277 | -0.17% |
| liquid_topix | up | 2025 | 1595 | 0.51% |
| liquid_topix | up | 2026 | 1625 | 1.26% |
| non_topix | down | 2024 | 58 | -0.02% |
| non_topix | down | 2025 | 472 | 0.00% |
| non_topix | down | 2026 | 403 | 0.76% |
| non_topix | up | 2024 | 101 | -0.11% |
| non_topix | up | 2025 | 876 | 0.15% |
| non_topix | up | 2026 | 617 | -1.04% |
| strong_liquid_topix | down | 2024 | 200 | -0.26% |
| strong_liquid_topix | down | 2025 | 1012 | -1.81% |
| strong_liquid_topix | down | 2026 | 1157 | -2.10% |
| strong_liquid_topix | up | 2024 | 140 | -0.09% |
| strong_liquid_topix | up | 2025 | 860 | 0.14% |
| strong_liquid_topix | up | 2026 | 956 | 1.12% |

2024・2025・2026年の固定条件結果は execution_year.parquet。5・20・30bpおよび0.1%参加率は execution_summary.parquet。売買代金上限と借株候補は事前情報。価格は分足約定の観測値で、板と受注を再現していない。
