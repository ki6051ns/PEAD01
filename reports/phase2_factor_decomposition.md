# Phase 2 ファクター分解

## Day 5 の同一サンプル比較

| signal | bucket | measure | 件数 | 銘柄数 | 平均 | 中央値 | 95%区間 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| initial | down | raw | 39250 | 4107 | -0.04% | -0.13% | -0.29% ～ 0.21% |
| initial | up | raw | 30496 | 4089 | 0.56% | -0.09% | 0.32% ～ 0.80% |
| initial | down | topix | 39250 | 4107 | -0.52% | -0.74% | -0.72% ～ -0.31% |
| initial | up | topix | 30496 | 4089 | 0.04% | -0.67% | -0.17% ～ 0.25% |
| initial | down | industry | 39250 | 4107 | -0.35% | -0.55% | -0.46% ～ -0.25% |
| initial | up | industry | 30496 | 4089 | 0.20% | -0.50% | 0.06% ～ 0.35% |
| initial | down | matched | 39250 | 4107 | -0.39% | -0.25% | -0.50% ～ -0.28% |
| initial | up | matched | 30496 | 4089 | 0.21% | -0.22% | 0.07% ～ 0.34% |
| revision | down | raw | 3374 | 1884 | 0.23% | 0.00% | -0.08% ～ 0.55% |
| revision | flat | raw | 36654 | 3841 | 0.24% | 0.00% | -0.04% ～ 0.52% |
| revision | up | raw | 5541 | 2318 | 0.96% | 0.28% | 0.61% ～ 1.32% |
| revision | down | topix | 3374 | 1884 | -0.21% | -0.44% | -0.50% ～ 0.07% |
| revision | flat | topix | 36654 | 3841 | -0.32% | -0.70% | -0.52% ～ -0.11% |
| revision | up | topix | 5541 | 2318 | 0.43% | -0.22% | 0.15% ～ 0.70% |
| revision | down | industry | 3374 | 1884 | -0.16% | -0.43% | -0.40% ～ 0.09% |
| revision | flat | industry | 36654 | 3841 | -0.18% | -0.54% | -0.29% ～ -0.08% |
| revision | up | industry | 5541 | 2318 | 0.48% | -0.12% | 0.26% ～ 0.70% |
| revision | down | matched | 3374 | 1884 | -0.14% | -0.14% | -0.49% ～ 0.21% |
| revision | flat | matched | 36654 | 3841 | -0.17% | -0.24% | -0.27% ～ -0.07% |
| revision | up | matched | 5541 | 2318 | 0.49% | 0.18% | 0.23% ～ 0.75% |

## マッチングの成立数

| initial | events | selected | returns | unmatched |
| --- | --- | --- | --- | --- |
| down | 41586 | 40547 | 39250 | 1039 |
| up | 32249 | 31434 | 30496 | 815 |

## Day 5 極端値の寄与

| 初動 | 絶対値上位20件の平均への符号付き寄与 |
| --- | --- |
| down | -0.01% |
| up | 0.05% |

## 初動・修正方向と属性を同時に比較

目的変数はマッチ後Day 5。初動正・据え置きを基準とする。Momentumは事前60営業日価格リターン。区間は銘柄・開示日の2方向クラスタ。同一対照の再利用による依存は残る。Valueは未調整。

| 集合 | 実績差調整 | 項 | 件数 | 係数 | 下限 | 上限 |
| --- | --- | --- | --- | --- | --- | --- |
| full | False | initial_down | 45225 | 0.54% | 0.20% | 0.87% |
| full | False | revision_up | 45225 | 0.32% | -0.04% | 0.67% |
| full | False | revision_down | 45225 | 1.20% | 0.23% | 2.16% |
| full | False | initial_down_revision_up | 45225 | -0.50% | -1.05% | 0.04% |
| full | False | initial_down_revision_down | 45225 | -1.23% | -2.22% | -0.25% |
| full | False | revision_up_given_initial_down | 45225 | -0.19% | -0.62% | 0.24% |
| surprise_observed | False | initial_down | 7309 | 0.62% | 0.10% | 1.14% |
| surprise_observed | False | revision_up | 7309 | -0.38% | -1.02% | 0.26% |
| surprise_observed | False | revision_down | 7309 | 1.01% | -0.64% | 2.66% |
| surprise_observed | False | initial_down_revision_up | 7309 | 1.10% | 0.04% | 2.16% |
| surprise_observed | False | initial_down_revision_down | 7309 | -1.14% | -2.84% | 0.56% |
| surprise_observed | False | revision_up_given_initial_down | 7309 | 0.72% | -0.13% | 1.57% |
| surprise_observed | True | initial_down | 7309 | 0.60% | 0.08% | 1.11% |
| surprise_observed | True | revision_up | 7309 | -0.35% | -0.99% | 0.28% |
| surprise_observed | True | revision_down | 7309 | 0.87% | -0.74% | 2.49% |
| surprise_observed | True | initial_down_revision_up | 7309 | 1.14% | 0.08% | 2.19% |
| surprise_observed | True | initial_down_revision_down | 7309 | -1.14% | -2.83% | 0.55% |
| surprise_observed | True | revision_up_given_initial_down | 7309 | 0.78% | -0.07% | 1.64% |

規模・業種・流動性・決算期・年・集中日・発表時刻の個別集計は stratified.parquet。
