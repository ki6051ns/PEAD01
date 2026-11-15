# Phase 9｜学習期間とWFの比較

[研究総括](../../research/phase9_summary.md)に主要14条件、参考のBlank Dynamic、Phase 7再現の結果を掲載した。WFの開始は2024-10-18、終了は2026-11-13、全504営業日。年率Sharpeは日次純リターンに252営業日を用いて年率化した。四半期・年次の比率は各期間で複利計算し、円寄与は継続NAVの台帳から合算する。2024Q4と2026Q4は部分四半期、2026年は11月13日まで。

## 成果物

| ファイル | 内容 |
| --- | --- |
| `performance.csv` | 学習期間・方式別の年率Sharpe、年率収益、最大DD、円損益、2025Q2および最良四半期を外したSharpe |
| [01_sharpe_heatmap.png](01_sharpe_heatmap.png) | 3方式×7窓。金枠と星1個はSharpe 1.5以上、星2個は2.0以上 |
| `quarterly.csv`、`annual.csv` | 暦四半期・暦年の純損益・収益率・Sharpe・約定等 |
| `phase7_reconciliation.csv` | 元台帳・更新日の再現、504日共通範囲、Phase 9での45日検証と検証なし |
| `legacy_order_daily.parquet` | Phase 8データ・旧更新日・同じ採用候補で、注文入力を旧候補順に揃えた順序診断 |
| `*_daily.parquet` | 日付、日初資産、日末NAV、日次損益、費用、約定数、稼働率 |
| `*_executions.parquet` | 実約定の入口・出口、モデル上の時刻、銘柄、イベントキー、約定代金、費用・寄与 |
| `*_selection.parquet` | 更新日、適用期末、正の採用ウェイトと候補仕様。ID −1は現金 |
| `verification.json`、`inputs.json` | 台帳・入力照合、入力ファイルと計算コードのSHA-256 |

Parquetの接頭辞は `primary` が14主要条件、`reference` がBlank Dynamic、`control` がPhase 9日程での45日検証、`archived` が旧Phase 7環境、`legacy_calendar` がPhase 8データで旧更新日を使う対照。約定の `side` は建玉方向で、決済側の売買は逆方向。ショート決済の `cost_yen` には当日計上の借株料が含まれ、保有中の日次費用は計算ディレクトリの `*_journal.parquet` と日次NAVに記録される。約定代金は入口費用とモデルの出口マークから計算した。

日次と約定・採用の詳細ファイルはローカルに保存する。Phase 10では同じ日付列から年次・半期・四半期・ローリング・累積区間を切り出せる。期初を変更して現金から始める場合は、期間を切り出した収益率と区別して台帳を再生する。

## 再現

リポジトリ直下で、Phase 8の完了キャッシュとPhase 7が参照した日足統一版のキャッシュを用意して実行する。APIの再取得は不要。

```powershell
$env:PYTHONPATH = 'src'
$env:OPENBLAS_NUM_THREADS = '1'
.venv/Scripts/python -m pead01.phase9 --source data/phase8_run --legacy data/phase6_daily_v4 --out data/phase9_run
.venv/Scripts/python -m pead01.phase9_report --source data/phase9_run
.venv/Scripts/python -m pytest -q
```

新しい入力で再計算する場合は別の `--out` を使用する。`--workers` で採点の並列数を指定できる。採点と台帳のチェックポイントは `--out` 以下に保存する。中断後に同じコマンドを実行すると、完成した採点・台帳を再利用する。

テスト54件が通過した。実データではPhase 8の拡張学習との日次完全一致、Phase 7の選択・台帳再現、21条件の件数、NAV・四半期純損益・約定件数の照合を確認した。
