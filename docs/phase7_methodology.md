# Phase 7 再現手順

日足統一版（ローカルコミット `58343a5`）の完了済み `data/phase6_daily_v4/` を入力にする。Phase 7 からそのディレクトリへの書き込みはない。旧 Phase 6 のチェックポイント自体を再開する場合は、チェックポイントのソースハッシュに対応する `58343a5` のコードを使う。

リポジトリ直下のPowerShellで実行する。

```powershell
$env:PYTHONPATH = 'src'
$env:OPENBLAS_NUM_THREADS = '1'
.\.venv\Scripts\python.exe -m pead01.phase7
.\.venv\Scripts\python.exe -m pytest -q
```

`data/phase7_v2/` に入力ハッシュ、円建て寄与の台帳、再選択・期間感応度のParquetを保存する。入力・コードが一致した再実行では完了済み台帳と再選択結果を再利用する。新規計算には別の `--output` を使う。出力に含まれる開示IDはローカルの集計キーで、公開レポートではイベント順位を表示する。

元の採用履歴を使う全156方式の切り出し評価と、Single・Neighborの252日学習・追加ブランク10日に限定した再選択を実施する。再選択は窓幅ごとに早期・中央・後期の3窓で行い、期初を変更した場合の感応度を検証する。元の採用履歴を窓内に限定した現金開始の対照を設け、持ち越し建玉の影響を比較する。更新タイミングと候補の変化はまとめて評価する。

- [Phase 7 研究総括](../research/phase7_summary.md)
- [評価窓ごとのSharpe](../figures/phase7/01_wf_window_sensitivity.png)
- [ブランク別の成績と日次相関](../figures/phase7/02_blank_surface_and_correlation.png)
- [利益集中と最大ドローダウン](../figures/phase7/03_profit_concentration_and_drawdown.png)
