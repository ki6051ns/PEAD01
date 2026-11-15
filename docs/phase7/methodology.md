# Phase 7 再現手順

日足統一版（ローカルコミット `58343a5`）の完了済み `data/phase6_daily_v4/` を入力にする。Phase 7 からそのディレクトリへの書き込みはない。Phase 6日足統一版の当時のチェックポイント自体を再開する場合は、チェックポイントのソースハッシュに対応する `58343a5` のコードを、記録した入力パスと一致する作業場所で使う。公開コードの対応コミットは `9d94f33`。

リポジトリ直下のPowerShellで実行する。

```powershell
$env:PYTHONPATH = 'src'
$env:OPENBLAS_NUM_THREADS = '1'
.\.venv\Scripts\python.exe -m pead01.phase7 --output data/phase7_repro --reports data/repro_phase7/reports --research data/repro_phase7/research --plots data/repro_phase7/figures
.\.venv\Scripts\python.exe -m pytest -q
```

上記では `data/phase7_repro/` に入力ハッシュ、円建て寄与の台帳、再選択・期間感応度のParquetを保存する。入力・コードが一致した再実行では完了済み台帳と再選択結果を再利用する。新規計算には別の `--output` を使う。再現用の文書・図は `data/repro_phase7/` に生成する。公開用の整理済み文書と図は下記を参照。出力に含まれる開示IDはローカルの集計キーで、公開レポートではイベント順位を表示する。

元の採用履歴を使う全156方式の切り出し評価と、Single・Neighborの252日学習・追加ブランク10日に限定した再選択を実施する。再選択は窓幅ごとに早期・中央・後期の3窓で行い、期初を変更した場合の感応度を検証する。元の採用履歴を窓内に限定した現金開始の対照を設け、持ち越し建玉の影響を比較する。更新タイミングと候補の変化はまとめて評価する。

- [Phase 7 研究総括](../../research/phase7_summary.md)
- [評価窓ごとのSharpe](../../figures/phase7/01_wf_window_sensitivity.png)
- [ブランク別の成績と日次相関](../../figures/phase7/02_blank_surface_and_correlation.png)
- [利益集中と最大ドローダウン](../../figures/phase7/03_profit_concentration_and_drawdown.png)

- [Phase 7の実装](../../src/pead01/phase7.py)

## 全方式・全期間の追加統計

[統合総括](../../research/phase7_summary.md)に、初動・保有期間、系列別、月・四半期・年、イベント集中の集計を収録した。[追加統計の実装](../../src/pead01/phase7_statistics.py)と[レポート生成](../../src/pead01/phase7_statistics_report.py)は、Phase 6の日足WF・採用履歴・価格経路を入力とする。候補選択をやり直さず、保存済みの資金台帳設定で全156方式の採用履歴を再生する。

```powershell
$env:PYTHONPATH = 'src'
$env:OPENBLAS_NUM_THREADS = '1'
.\.venv\Scripts\python.exe -m pead01.phase7_statistics_report
```

既定の入力は `data/phase6_daily_v4/`。入力のハッシュと再生後の集計キャッシュを `data/phase7_statistics/` に保存する。最初の実行は台帳再生を行い、同じ入力での再実行はキャッシュからCSV・図・Markdownを生成する。キャッシュはGitに含めない。整理済みの公開資料と別の場所へ書き出す場合は `--out`、`--research`、`--plots` を指定できる。

出力する [集計CSV](../../reports/phase7/tables/) の収益・稼働率は小数。期間損益は日次収益率の複利、日次費用・方向別グロス列の合計は記述統計、初動・保有期間・イベントの純寄与は初期資本を分母とした加算可能な帰属である。月・四半期・年の複利再結合と8項目の日次照合を方式ごとに検査する。公開CSVの最細粒度は方式×期間または方式×パラメータ区分とし、個別取引は含めない。
