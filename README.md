# PEAD01

日本株の決算発表後の価格形成と持続性を調べる Phase 1。価格反応を日次・分足で観察し、次の研究仮説を立てる。

## Windows での実行

Python 3.8 と既存認証済みの J-Quants CLI を使用した。PowerShell で以下を実行する。

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m pead01.acquire --from 2021-11-13 --to 2026-11-13 financials daily master topix calendar
.venv/Scripts/python -m pead01.acquire --from 2026-08-01 --to 2026-10-31 minute
.venv/Scripts/python -m pead01 --from 2021-11-13 --to 2026-11-13
```

分足取得は既存のアドオン権限を使用する。生ファイルと SHA-256・取得日・提供元の更新時刻は `data/raw/` に格納する。同じスナップショットで再計算する場合は最終行だけ実行する。再取得時は配信側の改訂および契約のローリング期間により結果が変化し得る。取得コマンドを同じ保存先で同時に実行する場合は、異なるデータセットを指定する。

イベント表・観測リターン・カバレッジ・グループ統計は `data/phase1/` の Parquet、レポートは [基礎結果](reports/phase1_baseline.md)、図表は [figures/](figures/) に出力する。入力・イベント単位の出力・認証情報はローカルで管理する。

[データ取得可能性](docs/phase1_data_sources.md) · [方法と品質検証](docs/phase1_methodology.md)

## Phase 2

Phase 1の保存済み出力と生データを使用する。PowerShellで `$env:PYTHONPATH = "src"` を設定し、`.venv/Scripts/python -m pead01.phase2` を実行する。イベント別パネル・比較統計は `data/phase2/` に保存する。

[結果](reports/phase2_findings.md) · [ファクター分解](reports/phase2_factor_decomposition.md) · [方法](docs/phase2_methodology.md)
