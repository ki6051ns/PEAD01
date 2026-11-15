# Phase 6 WF更新履歴（Q）

[比較レポートに戻る](phase6_ensemble_parameter_comparison.md)

<details>
<summary>dynamic_Q_126</summary>

| 開始 | 終了 | 記録数 | 正配分数 | 累計ID | 継続率 | HHI | 実効数 | 計測変化 | 保有変化 | 方向変化 | 日数 | 損益 | Sharpe | 最大DD | 稼働率 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-07-01 | 2025-09-30 | 10 | 7 | 7 | — | 0.31 | 3.23 | — | — | — | 62 | 0.69% | 2.76 | -0.21% | 3.80% |
| 2025-10-01 | 2025-12-30 | 10 | 4 | 11 | 0.00% | 0.59 | 1.71 | 25.14% | 89.04% | 54.47% | 62 | -0.00% | -0.04 | -0.25% | 1.21% |
| 2026-01-05 | 2026-03-31 | 10 | 10 | 21 | 0.00% | 0.63 | 1.59 | 71.68% | 67.29% | 12.95% | 58 | 0.14% | 3.10 | -0.05% | 1.99% |
| 2026-04-01 | 2026-06-30 | 10 | 7 | 27 | 14.29% | 0.37 | 2.71 | 82.80% | 83.02% | 83.02% | 61 | -0.61% | -3.46 | -0.65% | 0.99% |
| 2026-07-01 | 2026-09-30 | 10 | 7 | 33 | 0.00% | 0.46 | 2.16 | 51.29% | 100.00% | 90.72% | 61 | -0.01% | 0.02 | -2.68% | 26.20% |
| 2026-10-01 | 2026-11-13 | 10 | 4 | 36 | 25.00% | 0.47 | 2.14 | 1.17% | 32.96% | 3.78% | 30 | -0.05% | -2.31 | -0.10% | 1.19% |

<details>
<summary>2025-07-01〜2025-09-30 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 948da30989f7f621 | C | long | 7% | 40d | 10億円 | topix | any | fixed | 32 | 1 | 0.00% |
| 1bf2446bdd2afc14 | C | long | 0% | 20d | なし | all | rev_down | fixed | 48 | 2 | 8.71% |
| 56abf43639560d08 | C | long | 0% | 20d | なし | all | rev_conflict | fixed | 49 | 3 | 8.71% |
| 96c5ed45adbca50f | A | ls | 0% | 20d | なし | all | sector:非鉄金属 | fixed | 2 | 4 | 18.26% |
| f10a436863d3d843 | A | reverse | 0% | 3d | 10億円 | non_topix | any | fixed | 23 | 5 | 5.82% |
| d67d8495a7f764fd | C | ls | 7% | 30d | なし | non_topix | any | fixed | 42 | 6 | 0.00% |
| 7574c59daf66544a | A | reverse | 1% | 3d | 10億円 | non_topix | any | fixed | 9 | 7 | 5.14% |
| 94e5a9cf4ebf6297 | A | long | 0% | 20d | なし | all | sector:ガラス･土石製品 | fixed | 34 | 8 | 2.97% |
| 56860e534d79d09b | A | reverse | 3% | 2d | 10億円 | non_topix | any | fixed | 33 | 9 | 50.39% |
| 3e71d68a2f30a49d | C | long | 0% | 20d | なし | all | sector:医薬品 | fixed | 27 | 10 | 0.00% |
初動計測方式　A 82.59%, C 17.41%
保有・決済時点　20d 38.65%, 2d 50.39%, 30d 0.00%, 3d 10.96%, 40d 0.00%
方向　long 20.39%, ls 18.26%, reverse 61.35%

</details>

<details>
<summary>2025-10-01〜2025-12-30 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 89cf1ae453032027 | A | long | 3% | 10d | なし | non_topix | any | fixed | 35 | 1 | 0.00% |
| 38c20b49c4b8d66a | A | long | 0% | 3d | なし | all | sector:保険業 | fixed | 49 | 2 | 74.86% |
| a033278810ae853b | A | long | 1% | 10d | なし | non_topix | any | fixed | 32 | 3 | 0.00% |
| 4d5e4e87d6b50cd2 | A | long | 0% | 10d | なし | non_topix | any | fixed | 41 | 4 | 0.00% |
| 83d8e85119939c8e | C | long | 0% | 10d | 1億円 | non_topix | any | fixed | 44 | 5 | 0.00% |
| 2a1865d8180e67b1 | A | long | 1% | 10d | 1億円 | non_topix | any | fixed | 50 | 6 | 0.00% |
| 64fb683bf5b79661 | P5_15 | reverse | 3% | +60m from first | なし | non_topix | any | fixed | 23 | 7 | 6.67% |
| b5e58a68815462bb | A | long | 0% | 10d | 1億円 | non_topix | any | fixed | 48 | 8 | 0.00% |
| 7b65809f0fa4b1bc | P5_15 | reverse | 3% | +60m from first | 1億円 | non_topix | any | fixed | 20 | 9 | 5.31% |
| 786e9f6a8b59cff3 | P5_1 | ls | 0% | +60m from first | なし | all | afternoon | fixed | 27 | 10 | 13.16% |
初動計測方式　A 74.86%, C 0.00%, Intraday 25.14%
保有・決済時点　+60m from first 25.14%, 10d 0.00%, 3d 74.86%
方向　long 74.86%, ls 13.16%, reverse 11.98%

</details>

<details>
<summary>2026-01-05〜2026-03-31 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1b440fb9aca71f96 | P5_1 | long | 0% | +60m from first | なし | all | sector:建設業 | fixed | 6 | 1 | 78.25% |
| 408868790beb06d2 | C | short | 3% | 3d | 1億円 | non_topix | any | fixed | 18 | 2 | 1.34% |
| 034265a1d2455dd1 | C | short | 0% | 3d | 1億円 | non_topix | any | fixed | 32 | 3 | 0.11% |
| 0cb0a9a387000852 | A | short | 1% | 3d | 1億円 | non_topix | any | fixed | 29 | 4 | 2.15% |
| 88ee2eb9c147b90b | P5_1 | reverse | 7% | +60m from first | 10億円 | all | any | fixed | 21 | 5 | 1.59% |
| 257d3e8072ea76e0 | P5_1 | reverse | 3% | +60m from first | 10億円 | non_topix | any | fixed | 48 | 6 | 12.24% |
| 3615b08b74c4593b | A | short | 0% | 3d | 1億円 | non_topix | any | fixed | 47 | 7 | 0.82% |
| a36e553f181d002f | C | short | 3% | 5d | 1億円 | non_topix | any | fixed | 28 | 8 | 0.14% |
| 15ddb6dfe3efcaec | C | short | 7% | 3d | 1億円 | non_topix | any | fixed | 45 | 9 | 3.15% |
| 46eb4b9aece98c17 | A | ls | 0% | 20d | なし | all | busy_known | fixed | 4 | 10 | 0.21% |
初動計測方式　A 3.18%, C 4.74%, Intraday 92.08%
保有・決済時点　+60m from first 92.08%, 20d 0.21%, 3d 7.57%, 5d 0.14%
方向　long 78.25%, ls 0.21%, reverse 13.83%, short 7.71%

</details>

<details>
<summary>2026-04-01〜2026-06-30 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| a976590347527b0e | A | short | 0% | 3d | なし | all | sector:精密機器 | fixed | 5 | 1 | 47.47% |
| a36e553f181d002f | C | short | 3% | 5d | 1億円 | non_topix | any | fixed | 2 | 2 | 5.30% |
| 9f85740f3b3d4fd7 | C | short | 1% | 5d | 1億円 | non_topix | any | fixed | 7 | 3 | 1.13% |
| 5f755d10f315ac68 | C | short | 0% | 5d | 1億円 | non_topix | any | fixed | 4 | 4 | 0.00% |
| 6dd06d9eefad34a0 | P5_1 | long | 0% | +60m from first | なし | all | sector:サービス業 | fixed | 47 | 5 | 7.39% |
| b5b2d2a8770128c8 | P5_5 | long | 3% | +60m from first | なし | all | any | fixed | 33 | 6 | 1.82% |
| 4a12c6c292423609 | C | short | 0% | 3d | なし | all | sector:精密機器 | fixed | 3 | 7 | 36.83% |
| 3752f63429a72293 | P5_5 | long | 0% | +60m from first | なし | all | after_close | fixed | 36 | 8 | 0.00% |
| a00e36f8c512573d | P5_5 | long | 1% | +60m from first | なし | all | any | fixed | 19 | 9 | 0.00% |
| 2dd8963342bbd1ac | P5_5 | long | 1% | +60m from first | 1億円 | all | any | fixed | 26 | 10 | 0.07% |
初動計測方式　A 47.47%, C 43.26%, Intraday 9.28%
保有・決済時点　+60m from first 9.28%, 3d 84.30%, 5d 6.43%
方向　long 9.28%, short 90.72%

</details>

<details>
<summary>2026-07-01〜2026-09-30 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 96c5ed45adbca50f | A | ls | 0% | 20d | なし | all | sector:非鉄金属 | fixed | 33 | 1 | 61.39% |
| 94b292034b18db7f | A | long | 7% | 30d | 10億円 | topix | any | fixed | 4 | 2 | 28.83% |
| db129cc0deea8e33 | A | long | 0% | 30d | 10億円 | topix | any | fixed | 13 | 3 | 0.00% |
| 57ec03cd99659a3c | A | long | 3% | 30d | 10億円 | topix | any | fixed | 6 | 4 | 1.23% |
| 3d5c18a0136f8c5e | A | long | 1% | 30d | 10億円 | topix | any | fixed | 12 | 5 | 0.00% |
| ae6d30d45e73900b | A | long | 0% | 30d | 10億円 | all | any | fixed | 20 | 6 | 0.00% |
| 68b950dac62bbaee | A | long | 7% | 30d | 10億円 | all | any | fixed | 18 | 7 | 0.92% |
| e04fd4658a13eca3 | C | long | 3% | 30d | 1億円 | topix | any | fixed | 25 | 8 | 1.24% |
| d6236b071bd7991a | A | long | 0% | 20d | なし | all | past_size_high | fixed | 24 | 9 | 5.65% |
| ba2f9b2fb82c15cd | A | long | 3% | 30d | 1億円 | topix | any | fixed | 43 | 10 | 0.74% |
初動計測方式　A 98.76%, C 1.24%
保有・決済時点　20d 67.04%, 30d 32.96%
方向　long 38.61%, ls 61.39%

</details>

<details>
<summary>2026-10-01〜2026-11-13 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cbb32f7e54f019df | A | long | 0% | 20d | なし | all | sector:輸送用機器 | fixed | 38 | 1 | 42.32% |
| ea862019601cd475 | C | long | 0% | 60d | なし | all | afternoon | fixed | 9 | 2 | 0.00% |
| ba11518afd2c8c5f | C | long | 0% | 30d | 1億円 | topix | any | fixed | 31 | 3 | 0.00% |
| 7f0747d18e454aa0 | A | long | 0% | 60d | なし | all | afternoon | fixed | 8 | 4 | 0.00% |
| 5cc0c41159710542 | C | long | 1% | 30d | 1億円 | topix | any | fixed | 28 | 5 | 0.00% |
| 96c5ed45adbca50f | A | ls | 0% | 20d | なし | all | sector:非鉄金属 | fixed | 17 | 6 | 53.63% |
| a4bec343349636e1 | A | long | 0% | 20d | なし | all | afternoon | fixed | 19 | 7 | 0.00% |
| ed34c4e29913c739 | C | long | 0% | 20d | なし | all | afternoon | fixed | 6 | 8 | 0.00% |
| 694bad76c4018270 | C | long | 1% | 60d | 1億円 | topix | any | fixed | 48 | 9 | 0.07% |
| 8b89ec58c3cbc5ac | A | ls | 0% | 20d | なし | all | rev_up | fixed | 49 | 10 | 3.98% |
初動計測方式　A 99.93%, C 0.07%
保有・決済時点　20d 99.93%, 30d 0.00%, 60d 0.07%
方向　long 42.39%, ls 57.61%

</details>


</details>

<details>
<summary>dynamic_Q_252</summary>

| 開始 | 終了 | 記録数 | 正配分数 | 累計ID | 継続率 | HHI | 実効数 | 計測変化 | 保有変化 | 方向変化 | 日数 | 損益 | Sharpe | 最大DD | 稼働率 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-07-01 | 2025-09-30 | 10 | 6 | 6 | — | 0.40 | 2.48 | — | — | — | 62 | 0.47% | 1.78 | -0.37% | 17.00% |
| 2025-10-01 | 2025-12-30 | 10 | 9 | 15 | 0.00% | 0.26 | 3.83 | 63.46% | 99.48% | 82.99% | 62 | -0.63% | -2.08 | -1.08% | 19.12% |
| 2026-01-05 | 2026-03-31 | 10 | 9 | 24 | 0.00% | 0.52 | 1.94 | 36.14% | 36.14% | 83.10% | 58 | 0.10% | 2.60 | -0.06% | 0.76% |
| 2026-04-01 | 2026-06-30 | 10 | 8 | 32 | 0.00% | 0.46 | 2.16 | 12.87% | 13.28% | 74.93% | 61 | -0.00% | -0.08 | -0.07% | 0.58% |
| 2026-07-01 | 2026-09-30 | 10 | 8 | 39 | 0.00% | 0.87 | 1.16 | 6.64% | 6.64% | 81.40% | 61 | 0.03% | 1.08 | -0.04% | 0.65% |
| 2026-10-01 | 2026-11-13 | 10 | 8 | 45 | 0.00% | 0.32 | 3.13 | 3.45% | 6.52% | 94.26% | 30 | 0.01% | 2.30 | -0.01% | 0.37% |

<details>
<summary>2025-07-01〜2025-09-30 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6c604414bb9fdfa7 | A | ls | 7% | 90d | 10億円 | topix | any | fixed | 38 | 1 | 16.61% |
| 94b292034b18db7f | A | long | 7% | 30d | 10億円 | topix | any | fixed | 44 | 2 | 0.00% |
| ba5b3ec71699cdfc | C | long | 7% | 30d | 10億円 | topix | any | fixed | 39 | 3 | 0.11% |
| cb12132683f32fb4 | A | long | 7% | 40d | 10億円 | topix | any | fixed | 20 | 4 | 0.00% |
| 948da30989f7f621 | C | long | 7% | 40d | 10億円 | topix | any | fixed | 17 | 5 | 0.00% |
| f57c130157ee1565 | A | long | 7% | 15d | 10億円 | all | any | fixed | 36 | 6 | 0.71% |
| e25ef307325acb68 | C | long | 7% | 15d | 10億円 | all | any | fixed | 28 | 7 | 4.45% |
| 065b48aec41b4e32 | C | long | 7% | 40d | 10億円 | all | any | fixed | 43 | 8 | 0.00% |
| da2da72643e98955 | C | long | 7% | 10d | 10億円 | topix | any | fixed | 27 | 9 | 20.46% |
| 7d36d3a98cdfe774 | C | long | 0% | 60d | なし | all | rev_down | fixed | 40 | 10 | 57.66% |
初動計測方式　A 17.32%, C 82.68%
保有・決済時点　10d 20.46%, 15d 5.16%, 30d 0.11%, 40d 0.00%, 60d 57.66%, 90d 16.61%
方向　long 83.39%, ls 16.61%

</details>

<details>
<summary>2025-10-01〜2025-12-30 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cb12132683f32fb4 | A | long | 7% | 40d | 10億円 | topix | any | fixed | 37 | 1 | 0.00% |
| cce7326b0b45cd42 | A | long | 0% | 60d | なし | all | rev_down | fixed | 50 | 2 | 0.41% |
| 64fb683bf5b79661 | P5_15 | reverse | 3% | +60m from first | なし | non_topix | any | fixed | 25 | 3 | 7.03% |
| 26b8e66d768452d4 | C | ls | 7% | 30d | 10億円 | topix | any | fixed | 33 | 4 | 0.06% |
| 7b65809f0fa4b1bc | P5_15 | reverse | 3% | +60m from first | 1億円 | non_topix | any | fixed | 22 | 5 | 4.60% |
| 786e9f6a8b59cff3 | P5_1 | ls | 0% | +60m from first | なし | all | afternoon | fixed | 30 | 6 | 25.93% |
| 9ed88fec4f3cc98d | P5_15 | reverse | 1% | +60m from first | なし | non_topix | any | fixed | 9 | 7 | 2.11% |
| e6dab2bb0bc2583e | C | ls | 0% | 20d | なし | all | sector:水産・農林業 | fixed | 28 | 8 | 35.98% |
| 5d8652bcedcf42fe | C | ls | 7% | 30d | 10億円 | all | any | fixed | 47 | 9 | 0.10% |
| 7f178ced171bcd14 | P5_15 | reverse | 7% | +60m from first | 1億円 | non_topix | any | fixed | 41 | 10 | 23.78% |
初動計測方式　A 0.41%, C 36.14%, Intraday 63.46%
保有・決済時点　+60m from first 63.46%, 20d 35.98%, 30d 0.16%, 40d 0.00%, 60d 0.41%
方向　long 0.41%, ls 62.07%, reverse 37.52%

</details>

<details>
<summary>2026-01-05〜2026-03-31 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1b440fb9aca71f96 | P5_1 | long | 0% | +60m from first | なし | all | sector:建設業 | fixed | 5 | 1 | 70.64% |
| 855aabe9a7942891 | P5_1 | reverse | 0% | +60m from first | 10億円 | non_topix | any | fixed | 37 | 2 | 5.60% |
| a246e7a9bf691791 | A | short | 1% | 5d | 10億円 | non_topix | any | fixed | 47 | 3 | 0.79% |
| 1732df485821a392 | A | short | 0% | 5d | 10億円 | non_topix | any | fixed | 29 | 4 | 0.33% |
| 96c5ed45adbca50f | A | ls | 0% | 20d | なし | all | sector:非鉄金属 | fixed | 23 | 5 | 0.41% |
| 88ee2eb9c147b90b | P5_1 | reverse | 7% | +60m from first | 10億円 | all | any | fixed | 15 | 6 | 0.00% |
| 257d3e8072ea76e0 | P5_1 | reverse | 3% | +60m from first | 10億円 | non_topix | any | fixed | 30 | 7 | 6.95% |
| 3933b05201c30baa | A | short | 3% | 5d | 10億円 | non_topix | any | fixed | 34 | 8 | 3.15% |
| 894f7daf87385989 | P5_1 | reverse | 1% | +60m from first | 10億円 | non_topix | any | fixed | 40 | 9 | 3.54% |
| 955d5d7eb8b5ea27 | A | short | 0% | 1d | 10億円 | non_topix | any | fixed | 24 | 10 | 8.61% |
初動計測方式　A 13.28%, Intraday 86.72%
保有・決済時点　+60m from first 86.72%, 1d 8.61%, 20d 0.41%, 5d 4.27%
方向　long 70.64%, ls 0.41%, reverse 16.08%, short 12.87%

</details>

<details>
<summary>2026-04-01〜2026-06-30 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0170a76f84068203 | P5_15 | ls | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 28 | 1 | 12.64% |
| ce72146abbb9cbcb | P5_5 | long | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 31 | 2 | 10.97% |
| 6dd06d9eefad34a0 | P5_1 | long | 0% | +60m from first | なし | all | sector:サービス業 | fixed | 3 | 3 | 0.74% |
| b5b2d2a8770128c8 | P5_5 | long | 3% | +60m from first | なし | all | any | fixed | 26 | 4 | 0.08% |
| 70f56f6eb682fcc4 | A | short | 7% | 3d | 1億円 | non_topix | any | fixed | 48 | 5 | 0.41% |
| ccb4816ee9ac212e | P5_5 | ls | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 38 | 6 | 8.72% |
| a00e36f8c512573d | P5_5 | long | 1% | +60m from first | なし | all | any | fixed | 27 | 7 | 0.00% |
| 00351dbd14cc827e | P5_5 | long | 0% | +60m from first | なし | all | any | fixed | 29 | 8 | 0.00% |
| 2ff153b7652a298e | P5_1 | ls | 0% | +60m from first | なし | all | sector:サービス業 | fixed | 20 | 9 | 1.11% |
| f3b2382089e9f36c | P5_5 | short | 0% | +60m from first | なし | all | sector:食料品 | fixed | 6 | 10 | 65.33% |
初動計測方式　A 0.41%, Intraday 99.59%
保有・決済時点　+60m from first 99.59%, 3d 0.41%
方向　long 11.79%, ls 22.47%, short 65.75%

</details>

<details>
<summary>2026-07-01〜2026-09-30 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ef467fd6a08d32f7 | A | ls | 7% | 5d | なし | non_topix | any | fixed | 44 | 1 | 0.22% |
| 96c5ed45adbca50f | A | ls | 0% | 20d | なし | all | sector:非鉄金属 | fixed | 2 | 2 | 0.79% |
| 15ddb6dfe3efcaec | C | short | 7% | 3d | 1億円 | non_topix | any | fixed | 18 | 3 | 3.15% |
| 408868790beb06d2 | C | short | 3% | 3d | 1億円 | non_topix | any | fixed | 42 | 4 | 1.52% |
| 662eb9e0ea2b3598 | C | ls | 7% | 3d | なし | non_topix | any | fixed | 46 | 5 | 1.13% |
| 94b292034b18db7f | A | long | 7% | 30d | 10億円 | topix | any | fixed | 32 | 6 | 0.22% |
| 860472858213c6ed | P5_15 | long | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 30 | 7 | 92.95% |
| db129cc0deea8e33 | A | long | 0% | 30d | 10億円 | topix | any | fixed | 24 | 8 | 0.00% |
| 57ec03cd99659a3c | A | long | 3% | 30d | 10億円 | topix | any | fixed | 37 | 9 | 0.02% |
| 3d5c18a0136f8c5e | A | long | 1% | 30d | 10億円 | topix | any | fixed | 29 | 10 | 0.00% |
初動計測方式　A 1.25%, C 5.80%, Intraday 92.95%
保有・決済時点　+60m from first 92.95%, 20d 0.79%, 30d 0.24%, 3d 5.80%, 5d 0.22%
方向　long 93.19%, ls 2.14%, short 4.67%

</details>

<details>
<summary>2026-10-01〜2026-11-13 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ccb4816ee9ac212e | P5_5 | ls | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 14 | 1 | 38.19% |
| 60251e7e3f3894bc | P5_1 | ls | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 19 | 2 | 33.34% |
| a44dbb6696951084 | C | short | 3% | 2d | 1億円 | non_topix | any | fixed | 38 | 3 | 0.69% |
| 0170a76f84068203 | P5_15 | ls | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 25 | 4 | 24.87% |
| cbb32f7e54f019df | A | long | 0% | 20d | なし | all | sector:輸送用機器 | fixed | 42 | 5 | 0.52% |
| 065bb0040261311d | C | short | 3% | 1d | なし | non_topix | any | fixed | 29 | 6 | 0.00% |
| c0abb6d61925ddf7 | C | short | 3% | 1d | 1億円 | non_topix | any | fixed | 44 | 7 | 2.34% |
| ba11518afd2c8c5f | C | long | 0% | 30d | 1億円 | topix | any | fixed | 49 | 8 | 0.00% |
| e90f06ca10feada8 | A | long | 0% | 60d | なし | all | vol_high | fixed | 12 | 9 | 0.04% |
| 5cc0c41159710542 | C | long | 1% | 30d | 1億円 | topix | any | fixed | 50 | 10 | 0.00% |
初動計測方式　A 0.57%, C 3.03%, Intraday 96.40%
保有・決済時点　+60m from first 96.40%, 1d 2.34%, 20d 0.52%, 2d 0.69%, 30d 0.00%, 60d 0.04%
方向　long 0.57%, ls 96.40%, short 3.03%

</details>


</details>

<details>
<summary>dynamic_Q_504</summary>

| 開始 | 終了 | 記録数 | 正配分数 | 累計ID | 継続率 | HHI | 実効数 | 計測変化 | 保有変化 | 方向変化 | 日数 | 損益 | Sharpe | 最大DD | 稼働率 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-07-01 | 2025-09-30 | 10 | 6 | 6 | — | 0.34 | 2.98 | — | — | — | 62 | 0.77% | 2.70 | -0.28% | 7.63% |
| 2025-10-01 | 2025-12-30 | 10 | 5 | 11 | 0.00% | 0.33 | 3.01 | 36.21% | 3.52% | 0.00% | 62 | 0.33% | 1.32 | -0.56% | 3.09% |
| 2026-01-05 | 2026-03-31 | 10 | 10 | 19 | 20.00% | 0.63 | 1.59 | 96.17% | 97.98% | 20.04% | 58 | 0.13% | 2.98 | -0.06% | 0.56% |
| 2026-04-01 | 2026-06-30 | 10 | 8 | 27 | 0.00% | 0.47 | 2.15 | 3.83% | 3.83% | 85.96% | 61 | -0.01% | -0.17 | -0.07% | 0.39% |
| 2026-07-01 | 2026-09-30 | 10 | 8 | 31 | 0.00% | 0.87 | 1.15 | 1.09% | 1.09% | 81.68% | 61 | 0.07% | 1.55 | -0.02% | 0.25% |
| 2026-10-01 | 2026-11-13 | 10 | 10 | 34 | 20.00% | 0.30 | 3.34 | 0.87% | 0.87% | 26.80% | 30 | 0.05% | 5.52 | -0.00% | 0.19% |

<details>
<summary>2025-07-01〜2025-09-30 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| f57c130157ee1565 | A | long | 7% | 15d | 10億円 | all | any | fixed | 35 | 1 | 0.00% |
| e25ef307325acb68 | C | long | 7% | 15d | 10億円 | all | any | fixed | 36 | 2 | 1.07% |
| bd7c6e31495c0a31 | C | long | 7% | 15d | 10億円 | topix | any | fixed | 31 | 3 | 2.45% |
| b85808248cfd5f2b | A | long | 3% | 15d | 10億円 | all | any | fixed | 32 | 4 | 0.00% |
| 1d0c03bd10d550a1 | C | long | 3% | 15d | 10億円 | topix | any | fixed | 38 | 5 | 0.00% |
| 7e98d07ddf977c76 | C | long | 1% | 15d | 10億円 | all | any | fixed | 45 | 6 | 0.00% |
| 689b520baef83b99 | A | long | 0% | 20d | なし | all | lunch | fixed | 12 | 7 | 7.66% |
| 1bf2446bdd2afc14 | C | long | 0% | 20d | なし | all | rev_down | fixed | 5 | 8 | 40.06% |
| 56abf43639560d08 | C | long | 0% | 20d | なし | all | rev_conflict | fixed | 6 | 9 | 40.06% |
| d47c1dbd97eae0d3 | C | long | 0% | 20d | なし | all | lunch | fixed | 47 | 10 | 8.69% |
初動計測方式　A 7.66%, C 92.34%
保有・決済時点　15d 3.52%, 20d 96.48%
方向　long 100.00%

</details>

<details>
<summary>2025-10-01〜2025-12-30 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b3894500a40988b5 | A | long | 0% | 20d | なし | all | sector:鉄鋼 | fixed | 24 | 1 | 4.22% |
| 338ce57e5efc9042 | C | long | 0% | 20d | なし | all | sector:ゴム製品 | fixed | 40 | 2 | 38.78% |
| dc393799b6b7f6c2 | A | long | 0% | 20d | なし | all | sector:ゴム製品 | fixed | 46 | 3 | 39.65% |
| 7f5d560ecaa5f33d | C | long | 0% | 20d | なし | all | sector:卸売業 | fixed | 34 | 4 | 0.00% |
| d4fd6c571a92a40a | A | long | 0% | 20d | なし | all | sector:卸売業 | fixed | 41 | 5 | 0.00% |
| a4eaba0bb27bdc2a | A | long | 3% | 15d | 10億円 | topix | any | fixed | 28 | 6 | 0.00% |
| ccf5e5d3a5c14d5e | C | long | 0% | 20d | なし | all | sector:ガラス･土石製品 | fixed | 8 | 7 | 2.63% |
| cce7326b0b45cd42 | A | long | 0% | 60d | なし | all | rev_down | fixed | 47 | 8 | 0.00% |
| 05ea91e30aefd931 | A | long | 0% | 60d | なし | all | rev_conflict | fixed | 48 | 9 | 0.00% |
| 11c8f60972eb1f67 | C | long | 0% | 20d | なし | all | morning | fixed | 50 | 10 | 14.72% |
初動計測方式　A 43.87%, C 56.13%
保有・決済時点　15d 0.00%, 20d 100.00%, 60d 0.00%
方向　long 100.00%

</details>

<details>
<summary>2026-01-05〜2026-03-31 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3c234d1fd7a83f85 | A | ls | 0% | 20d | なし | all | sector:ガラス･土石製品 | fixed | 23 | 1 | 0.12% |
| 94e5a9cf4ebf6297 | A | long | 0% | 20d | なし | all | sector:ガラス･土石製品 | fixed | 12 | 2 | 0.18% |
| 1b440fb9aca71f96 | P5_1 | long | 0% | +60m from first | なし | all | sector:建設業 | fixed | 6 | 3 | 78.28% |
| ccf5e5d3a5c14d5e | C | long | 0% | 20d | なし | all | sector:ガラス･土石製品 | fixed | 13 | 4 | 0.09% |
| dc393799b6b7f6c2 | A | long | 0% | 20d | なし | all | sector:ゴム製品 | fixed | 42 | 5 | 1.41% |
| 855aabe9a7942891 | P5_1 | reverse | 0% | +60m from first | 10億円 | non_topix | any | fixed | 47 | 6 | 8.49% |
| 1732df485821a392 | A | short | 0% | 5d | 10億円 | non_topix | any | fixed | 17 | 7 | 1.81% |
| 96c5ed45adbca50f | A | ls | 0% | 20d | なし | all | sector:非鉄金属 | fixed | 46 | 8 | 0.22% |
| 88ee2eb9c147b90b | P5_1 | reverse | 7% | +60m from first | 10億円 | all | any | fixed | 19 | 9 | 0.37% |
| 257d3e8072ea76e0 | P5_1 | reverse | 3% | +60m from first | 10億円 | non_topix | any | fixed | 37 | 10 | 9.02% |
初動計測方式　A 3.73%, C 0.09%, Intraday 96.17%
保有・決済時点　+60m from first 96.17%, 20d 2.02%, 5d 1.81%
方向　long 79.96%, ls 0.34%, reverse 17.89%, short 1.81%

</details>

<details>
<summary>2026-04-01〜2026-06-30 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0170a76f84068203 | P5_15 | ls | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 35 | 1 | 12.72% |
| ce72146abbb9cbcb | P5_5 | long | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 38 | 2 | 11.05% |
| 6dd06d9eefad34a0 | P5_1 | long | 0% | +60m from first | なし | all | sector:サービス業 | fixed | 6 | 3 | 0.68% |
| b5b2d2a8770128c8 | P5_5 | long | 3% | +60m from first | なし | all | any | fixed | 33 | 4 | 0.06% |
| ccb4816ee9ac212e | P5_5 | ls | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 48 | 5 | 8.80% |
| a00e36f8c512573d | P5_5 | long | 1% | +60m from first | なし | all | any | fixed | 34 | 6 | 0.00% |
| 00351dbd14cc827e | P5_5 | long | 0% | +60m from first | なし | all | any | fixed | 36 | 7 | 0.00% |
| 2ff153b7652a298e | P5_1 | ls | 0% | +60m from first | なし | all | sector:サービス業 | fixed | 27 | 8 | 1.05% |
| f3b2382089e9f36c | P5_5 | short | 0% | +60m from first | なし | all | sector:食料品 | fixed | 12 | 9 | 65.53% |
| 654de52e93bb3af5 | P5_5 | long | 0% | +60m from first | なし | all | sector:サービス業 | fixed | 8 | 10 | 0.11% |
初動計測方式　Intraday 100.00%
保有・決済時点　+60m from first 100.00%
方向　long 11.89%, ls 22.57%, short 65.53%

</details>

<details>
<summary>2026-07-01〜2026-09-30 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 63bff39ee72a186c | P5_1 | short | 0% | +60m from first | なし | all | afternoon | fixed | 32 | 1 | 5.85% |
| 6008957fe016d1fc | P5_1 | long | 0% | +60m from first | なし | all | sector:繊維製品 | fixed | 27 | 2 | 93.06% |
| 96c5ed45adbca50f | A | ls | 0% | 20d | なし | all | sector:非鉄金属 | fixed | 2 | 3 | 0.16% |
| 1bf2446bdd2afc14 | C | long | 0% | 20d | なし | all | rev_down | fixed | 20 | 4 | 0.02% |
| 56abf43639560d08 | C | long | 0% | 20d | なし | all | rev_conflict | fixed | 21 | 5 | 0.02% |
| 83f7b4ed3fb11b07 | A | long | 0% | 20d | なし | all | rev_down | fixed | 46 | 6 | 0.00% |
| 9c1d699476d8f364 | A | long | 0% | 20d | なし | all | rev_conflict | fixed | 47 | 7 | 0.00% |
| 94e5a9cf4ebf6297 | A | long | 0% | 20d | なし | all | sector:ガラス･土石製品 | fixed | 8 | 8 | 0.48% |
| 6c604414bb9fdfa7 | A | ls | 7% | 90d | 10億円 | topix | any | fixed | 33 | 9 | 0.06% |
| 2c32c89ab0c64a71 | C | ls | 0% | 20d | なし | all | sector:非鉄金属 | fixed | 6 | 10 | 0.35% |
初動計測方式　A 0.70%, C 0.39%, Intraday 98.91%
保有・決済時点　+60m from first 98.91%, 20d 1.03%, 90d 0.06%
方向　long 93.58%, ls 0.57%, short 5.85%

</details>

<details>
<summary>2026-10-01〜2026-11-13 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 860472858213c6ed | P5_15 | long | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 21 | 1 | 7.62% |
| 6dd06d9eefad34a0 | P5_1 | long | 0% | +60m from first | なし | all | sector:サービス業 | fixed | 34 | 2 | 1.06% |
| ce72146abbb9cbcb | P5_5 | long | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 23 | 3 | 14.15% |
| ccb4816ee9ac212e | P5_5 | ls | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 6 | 4 | 8.81% |
| 6008957fe016d1fc | P5_1 | long | 0% | +60m from first | なし | all | sector:繊維製品 | fixed | 35 | 5 | 49.71% |
| 60251e7e3f3894bc | P5_1 | ls | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 13 | 6 | 12.24% |
| 0170a76f84068203 | P5_15 | ls | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 4 | 7 | 6.21% |
| 689b520baef83b99 | A | long | 0% | 20d | なし | all | lunch | fixed | 8 | 8 | 0.02% |
| 96c5ed45adbca50f | A | ls | 0% | 20d | なし | all | sector:非鉄金属 | fixed | 1 | 9 | 0.12% |
| 5a8c01df980175e3 | C | long | 0% | 20d | なし | all | sector:建設業 | fixed | 22 | 10 | 0.07% |
初動計測方式　A 0.15%, C 0.07%, Intraday 99.79%
保有・決済時点　+60m from first 99.79%, 20d 0.21%
方向　long 72.63%, ls 27.37%

</details>


</details>

<details>
<summary>dynamic_Q_0</summary>

| 開始 | 終了 | 記録数 | 正配分数 | 累計ID | 継続率 | HHI | 実効数 | 計測変化 | 保有変化 | 方向変化 | 日数 | 損益 | Sharpe | 最大DD | 稼働率 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-07-01 | 2025-09-30 | 10 | 3 | 3 | — | 0.78 | 1.28 | — | — | — | 62 | 0.20% | 2.91 | -0.05% | 2.08% |
| 2025-10-01 | 2025-12-30 | 10 | 8 | 11 | 0.00% | 0.31 | 3.19 | 19.02% | 0.98% | 0.00% | 62 | 0.51% | 2.31 | -0.23% | 3.13% |
| 2026-01-05 | 2026-03-31 | 10 | 9 | 17 | 33.33% | 0.87 | 1.14 | 97.56% | 99.01% | 6.29% | 58 | 0.19% | 3.34 | -0.07% | 0.76% |
| 2026-04-01 | 2026-06-30 | 10 | 10 | 24 | 10.00% | 0.90 | 1.11 | 0.55% | 1.09% | 95.50% | 61 | 0.00% | 0.07 | -0.09% | 0.53% |
| 2026-07-01 | 2026-09-30 | 10 | 8 | 28 | 12.50% | 0.37 | 2.69 | 97.20% | 99.56% | 97.05% | 61 | -0.14% | -1.43 | -0.18% | 1.46% |
| 2026-10-01 | 2026-11-13 | 10 | 8 | 33 | 12.50% | 0.21 | 4.75 | 98.73% | 98.73% | 52.19% | 30 | -0.01% | -2.19 | -0.01% | 0.14% |

<details>
<summary>2025-07-01〜2025-09-30 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| d154b687a79ba276 | C | long | 0% | 20d | なし | all | sector:倉庫･運輸関連業 | fixed | 46 | 1 | 87.89% |
| e25ef307325acb68 | C | long | 7% | 15d | 10億円 | all | any | fixed | 35 | 2 | 0.00% |
| 7d36d3a98cdfe774 | C | long | 0% | 60d | なし | all | rev_down | fixed | 33 | 3 | 0.00% |
| 98e238256d350f19 | C | long | 0% | 60d | なし | all | rev_conflict | fixed | 34 | 4 | 0.00% |
| bd7c6e31495c0a31 | C | long | 7% | 15d | 10億円 | topix | any | fixed | 27 | 5 | 0.00% |
| 689b520baef83b99 | A | long | 0% | 20d | なし | all | lunch | fixed | 16 | 6 | 0.00% |
| 1bf2446bdd2afc14 | C | long | 0% | 20d | なし | all | rev_down | fixed | 4 | 7 | 6.05% |
| 56abf43639560d08 | C | long | 0% | 20d | なし | all | rev_conflict | fixed | 5 | 8 | 6.05% |
| c4109646fd7bfcb8 | A | long | 7% | 15d | 10億円 | topix | any | fixed | 19 | 9 | 0.00% |
| cce7326b0b45cd42 | A | long | 0% | 60d | なし | all | rev_down | fixed | 50 | 10 | 0.00% |
初動計測方式　A 0.00%, C 100.00%
保有・決済時点　15d 0.00%, 20d 100.00%, 60d 0.00%
方向　long 100.00%

</details>

<details>
<summary>2025-10-01〜2025-12-30 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bc8fe6e5cead67c2 | C | long | 0% | 20d | なし | all | sector:鉄鋼 | fixed | 37 | 1 | 1.96% |
| 434f955eb0779b69 | C | long | 0% | 20d | なし | all | sector:非鉄金属 | fixed | 49 | 2 | 26.04% |
| b3894500a40988b5 | A | long | 0% | 20d | なし | all | sector:鉄鋼 | fixed | 26 | 3 | 1.55% |
| bead3736a2a3a4ea | A | long | 0% | 20d | なし | all | sector:機械 | fixed | 38 | 4 | 0.00% |
| c57b8810940f9060 | C | long | 0% | 20d | なし | all | sector:海運業 | fixed | 2 | 5 | 46.16% |
| d4fd6c571a92a40a | A | long | 0% | 20d | なし | all | sector:卸売業 | fixed | 35 | 6 | 0.00% |
| d0105d6ab72c06e5 | A | long | 0% | 20d | なし | all | morning | fixed | 17 | 7 | 16.49% |
| ccf5e5d3a5c14d5e | C | long | 0% | 20d | なし | all | sector:ガラス･土石製品 | fixed | 41 | 8 | 6.82% |
| cce7326b0b45cd42 | A | long | 0% | 60d | なし | all | rev_down | fixed | 47 | 9 | 0.49% |
| 05ea91e30aefd931 | A | long | 0% | 60d | なし | all | rev_conflict | fixed | 48 | 10 | 0.49% |
初動計測方式　A 19.02%, C 80.98%
保有・決済時点　20d 99.02%, 60d 0.98%
方向　long 100.00%

</details>

<details>
<summary>2026-01-05〜2026-03-31 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| efb6f8f881d3a07d | C | ls | 0% | 20d | なし | all | sector:海運業 | fixed | 39 | 1 | 0.66% |
| 689b520baef83b99 | A | long | 0% | 20d | なし | all | lunch | fixed | 30 | 2 | 0.00% |
| 94e5a9cf4ebf6297 | A | long | 0% | 20d | なし | all | sector:ガラス･土石製品 | fixed | 32 | 3 | 0.12% |
| 1b440fb9aca71f96 | P5_1 | long | 0% | +60m from first | なし | all | sector:建設業 | fixed | 7 | 4 | 93.38% |
| ccf5e5d3a5c14d5e | C | long | 0% | 20d | なし | all | sector:ガラス･土石製品 | fixed | 27 | 5 | 0.06% |
| 15f7235afc16e4a1 | A | ls | 3% | 10d | なし | non_topix | any | fixed | 29 | 6 | 0.01% |
| bc8fe6e5cead67c2 | C | long | 0% | 20d | なし | all | sector:鉄鋼 | fixed | 21 | 7 | 0.07% |
| b3894500a40988b5 | A | long | 0% | 20d | なし | all | sector:鉄鋼 | fixed | 17 | 8 | 0.08% |
| 1732df485821a392 | A | short | 0% | 5d | 10億円 | non_topix | any | fixed | 8 | 9 | 1.44% |
| 88ee2eb9c147b90b | P5_1 | reverse | 7% | +60m from first | 10億円 | all | any | fixed | 25 | 10 | 4.18% |
初動計測方式　A 1.65%, C 0.79%, Intraday 97.56%
保有・決済時点　+60m from first 97.56%, 10d 0.01%, 20d 0.99%, 5d 1.44%
方向　long 93.71%, ls 0.67%, reverse 4.18%, short 1.44%

</details>

<details>
<summary>2026-04-01〜2026-06-30 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1732df485821a392 | A | short | 0% | 5d | 10億円 | non_topix | any | fixed | 35 | 1 | 1.27% |
| 6dd06d9eefad34a0 | P5_1 | long | 0% | +60m from first | なし | all | sector:サービス業 | fixed | 10 | 2 | 0.55% |
| c57b8810940f9060 | C | long | 0% | 20d | なし | all | sector:海運業 | fixed | 2 | 3 | 0.17% |
| 7dc1728329701c41 | A | long | 0% | 20d | なし | all | sector:海運業 | fixed | 1 | 4 | 0.19% |
| 2ff153b7652a298e | P5_1 | ls | 0% | +60m from first | なし | all | sector:サービス業 | fixed | 46 | 5 | 0.27% |
| f3b2382089e9f36c | P5_5 | short | 0% | +60m from first | なし | all | sector:食料品 | fixed | 20 | 6 | 94.97% |
| 654de52e93bb3af5 | P5_5 | long | 0% | +60m from first | なし | all | sector:サービス業 | fixed | 11 | 7 | 0.54% |
| 3a4d2f0bd25a226a | P5_15 | long | 3% | +60m from first | なし | non_topix | any | fixed | 43 | 8 | 0.86% |
| 5ca4a7d6a298450e | C | ls | 0% | 60d | なし | all | before_open | fixed | 19 | 9 | 1.09% |
| 1bf2446bdd2afc14 | C | long | 0% | 20d | なし | all | rev_down | fixed | 6 | 10 | 0.08% |
初動計測方式　A 1.46%, C 1.34%, Intraday 97.20%
保有・決済時点　+60m from first 97.20%, 20d 0.44%, 5d 1.27%, 60d 1.09%
方向　long 2.40%, ls 1.36%, short 96.24%

</details>

<details>
<summary>2026-07-01〜2026-09-30 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 11c8f60972eb1f67 | C | long | 0% | 20d | なし | all | morning | fixed | 11 | 1 | 5.73% |
| 1bf2446bdd2afc14 | C | long | 0% | 20d | なし | all | rev_down | fixed | 7 | 2 | 1.95% |
| 56abf43639560d08 | C | long | 0% | 20d | なし | all | rev_conflict | fixed | 8 | 3 | 1.95% |
| dc393799b6b7f6c2 | A | long | 0% | 20d | なし | all | sector:ゴム製品 | fixed | 36 | 4 | 47.04% |
| 338ce57e5efc9042 | C | long | 0% | 20d | なし | all | sector:ゴム製品 | fixed | 43 | 5 | 38.06% |
| 94e5a9cf4ebf6297 | A | long | 0% | 20d | なし | all | sector:ガラス･土石製品 | fixed | 20 | 6 | 0.40% |
| d0105d6ab72c06e5 | A | long | 0% | 20d | なし | all | morning | fixed | 21 | 7 | 4.32% |
| 6c604414bb9fdfa7 | A | ls | 7% | 90d | 10億円 | topix | any | fixed | 32 | 8 | 0.55% |
| ccf5e5d3a5c14d5e | C | long | 0% | 20d | なし | all | sector:ガラス･土石製品 | fixed | 19 | 9 | 0.00% |
| 94b292034b18db7f | A | long | 7% | 30d | 10億円 | topix | any | fixed | 44 | 10 | 0.00% |
初動計測方式　A 52.31%, C 47.69%
保有・決済時点　20d 99.45%, 30d 0.00%, 90d 0.55%
方向　long 99.45%, ls 0.55%

</details>

<details>
<summary>2026-10-01〜2026-11-13 採用条件</summary>

| 候補ID | 計測 | 方向 | 閾値 | 保有 | 最低ADV | 対象 | 追加条件 | 決済 | 学習順位 | 検証順位 | 配分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2eee0e6ac8601c4e | A | long | 0% | 20d | なし | all | sector:電気･ガス業 | fixed | 35 | 1 | 0.00% |
| 860472858213c6ed | P5_15 | long | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 38 | 2 | 16.92% |
| 7dc1728329701c41 | A | long | 0% | 20d | なし | all | sector:海運業 | fixed | 2 | 3 | 0.32% |
| ce72146abbb9cbcb | P5_5 | long | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 40 | 4 | 29.06% |
| ccb4816ee9ac212e | P5_5 | ls | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 18 | 5 | 18.78% |
| 60251e7e3f3894bc | P5_1 | ls | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 33 | 6 | 21.66% |
| 11c8f60972eb1f67 | C | long | 0% | 20d | なし | all | morning | fixed | 19 | 7 | 0.17% |
| c57b8810940f9060 | C | long | 0% | 20d | なし | all | sector:海運業 | fixed | 4 | 8 | 0.78% |
| 0170a76f84068203 | P5_15 | ls | 0% | +60m from first | なし | all | sector:証券･商品先物取引業 | fixed | 14 | 9 | 12.30% |
| cbb32f7e54f019df | A | long | 0% | 20d | なし | all | sector:輸送用機器 | fixed | 32 | 10 | 0.00% |
初動計測方式　A 0.32%, C 0.95%, Intraday 98.73%
保有・決済時点　+60m from first 98.73%, 20d 1.27%
方向　long 47.26%, ls 52.74%

</details>


</details>
