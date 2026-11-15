# Phase 8｜集計と再現

[研究総括](../../research/phase8_summary.md)に主要な結果と解釈を記載した。生データ、日次の個別取引台帳、イベントIDはローカルの `data/` 以下で管理する。

## 実行手順

リポジトリ直下のPowerShellで実行する。J-Quants Standardで認証済みの公式CLIと、`requirements.txt` をインストール済みの仮想環境を使用する。取得をやり直すと、その時点のサービス提供期間内で選ばれるファイルが変わる場合がある。当時と同じデータでの再現には `inputs.json` に対応する保存済みアーカイブを使う。

```powershell
$env:PYTHONPATH = 'src'
$env:OPENBLAS_NUM_THREADS = '1'
.venv/Scripts/python -m pead01.acquire --root data/phase8_raw --from 2016-11-15 --to 2026-11-13 calendar topix financials master daily
.venv/Scripts/python -m pead01.phase8
.venv/Scripts/python -m pead01.phase8_report --target data/phase8_repro_report --summary data/phase8_repro_report/summary.md
.venv/Scripts/python -m pytest -q
```

過去アーカイブは `data/raw`、旧イベントは `data/phase2/events.parquet` が既定。保存場所が異なる場合は `--old-raw` と `--old-events` を指定する。旧アーカイブが無い環境では `--no-overlap` で照合を省略できる。

取得済みファイル、候補経路、候補採点、完了済みWF条件を再利用する。検証計算の停止は Ctrl+C、または `data/phase8_run/pause` を作成して次のチェックポイントで停止する。再開はそのファイルを除き、同じコマンドを実行する。`progress.json` に計算の段階と完了済み条件、`status.json` に状態や例外を記録する。入力・設定・計算コードのSHA-256が変わったときは新しい `--out` を使う。集計側の `--source` も対応させる。

## 表・図

| ファイル | 内容 |
| --- | --- |
| `performance.csv` | 年率、Sharpe、最大DD、純損益・費用の円換算、約定、稼働率、四半期安定性、2025Q2・利益上位イベントを除いたSharpe |
| `quarterly.csv` | 暦四半期の純リターン、Sharpe、約定数 |
| `jaccard.csv` | 隣接更新の候補Jaccard、前期残存率、現金を含む配分変化 |
| `selection.csv`、`selection_mix.csv` | 更新期の候補、初動・方向・保有ごとの採用ウェイト。候補ID −1 は現金 |
| `attribution.csv`、`regimes.csv` | 正味約定からの加算可能な純円寄与。市場環境は前日までのTOPIXの63営業日騰落率 |
| `correlations.csv`、`diagnostics.csv` | 学習・検証・次期成績の順位相関と、内訳となる候補スコア・適格性 |
| `wealth.csv` | 費用控除後の日次資産指数（初期値1） |
| `boundaries.csv` | 全更新期×ブランクの境界。開始は含み終了は除く。境界インデックスは0始まり。最終日はその翌位置を排他的終了とし日付欄は空欄 |
| `quality.json`、`inputs.json`、`config.json`、`progress.json` | アーカイブ照合、品質・再現条件、処理の完了記録 |
| `raw_key_audit.jsonl` | 実行時の独立確認。ファイル内の主キー重複と、複数ファイルに分かれた日付数。主キーは営業日・TOPIXが日付、日足・マスターが日付とコード、決算が開示日・コード・開示番号 |
| `environment.json`、`verification.json` | 実行時のライブラリ、全条件の期間・決済境界・候補集合検証、代表3条件の完全一致再計算 |

比率は小数、損益と費用の円換算は日初NAVでリンクする。上位10イベント集中度の分母は正のイベント純寄与合計。上位イベント除外は日次帰属の控除で求める。注文自体を除外した反実仮想の資金台帳とは異なる。内部検証との相関には、次期区間内に決済を確認した候補別の一次採点系列を使う。実約定を共有するアンサンブルの損益は共通台帳で別途評価する。

- [内部検証期間とWF Sharpe](01_duration.png)
- [Neighborの暦四半期リターン](02_quarterly.png)
- [Neighborの採用Jaccard](03_jaccard.png)
- [内部検証Sharpeと次期候補リターン](04_predictive.png)
- [ブランクアンサンブルの累積損益](05_blank_ensemble.png)
- [検証期間別Sharpeヒートマップ](06_sharpe_heatmap.png)（比較A・基準更新日程、検証ありは再ランキング）
