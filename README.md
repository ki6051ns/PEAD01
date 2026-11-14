# PEAD01｜日本株・決算発表後ドリフト戦略の研究

**PEAD（Post-Earnings Announcement Drift：決算発表後ドリフト）**を対象に、日本株の決算発表後の価格形成を研究するプロジェクトです。

決算情報が株価へ段階的に織り込まれるという経済的仮説を起点に、売買ルールの構築、高次元パラメータ探索、アンサンブル、信用取引を含む資金配分を検証します。

## PEAD01の二大ポイント：収益源泉 × 最適化

**① 収益源泉を経済的に説明すること**と、**② その収益機会を売買ルール・資金配分の最適化で引き出すこと**を研究の二本柱としています。

```mermaid
flowchart TB
    subgraph ECON["① 収益源泉｜なぜ利益が生まれるのか"]
      direction TB
      A["企業の決算発表・業績情報"] --> B["市場参加者の評価・売買が時間差で進む"]
      B --> C["発表直後の株価変動（初動）"]
      C --> D["価格の継続（ドリフト）・反転の可能性"]
    end
    subgraph OPT["② 最適化｜どう利益を獲得するか"]
      direction TB
      E["初動の強さ・銘柄条件・売買時刻を設定"] --> F["保有期間・売買方向のパラメータ探索"]
      F --> G["複数条件の組み合わせ（アンサンブル）"]
      G --> H["資金配分・信用取引・売買費用を調整"]
    end
    D --> E
    H --> I["WF（過去で選択し次の期間で評価）"]
    I --> J["Sharpe・年率収益・最大DD・稼働率"]
    J --> K["未観測OOSと約定可能性の検証（今後）"]
    classDef economic fill:#e8f2ff,stroke:#4578ae,color:#153455
    classDef optimize fill:#e8f7ee,stroke:#4c9669,color:#173e2c
    classDef check fill:#f5f1e8,stroke:#a18b64,color:#463c25
    class A,B,C,D economic
    class E,F,G,H optimize
    class I,J,K check
```

**戦略の考え方：** 決算後の価格反応を収益機会として捉え（経済的仮説）、条件探索・複数戦略の組み合わせ・資金管理によって実行可能性と収益効率を高めます。図は仮説と検証設計を示すもので、収益の再現性を保証するものではありません。

## 研究状況（2026年11月14日時点）

**Phase 1〜6.1の探索研究を完了しました。** 以下は過去データに基づくシミュレーションであり、実運用実績ではありません。研究過程で既に参照した期間のウォークフォワード（WF）成績を含むため、**未観測の独立OOS（Out-of-Sample）成績ではありません**。

| フェーズ | 主な結果 |
| --- | --- |
| Phase 1〜2 | 約75,369件の決算イベントから、決算直後の初動と、その後の相対リターンの関係を検証 |
| Phase 3 | 単純な20営業日ロング：年率収益 **6.16%**、Sharpe **0.62**、最大DD **−17.70%**（1,221営業日） |
| Phase 4〜5 | 分足で初動と約定タイミングを分析。短期の収益機会は小さく、コスト・エントリー遅延の影響が大きい |
| Phase 6 | 14,909候補の一次探索、上位20件の制約付き再評価。Single（単独の最良条件）のWF Sharpe **2.07**、年率収益 **1.93%** |
| Phase 6.1 | 資金配分・信用倍率の903ケースを評価。選択型WFのSingleは費用控除後Sharpe **2.02**、年率 **1.88%**。複合Shrink（共分散縮小による配分調整）はSharpe **1.58**、年率 **2.28%** |

高Sharpe候補の平均資金稼働率は約1.6〜2.6%と低く、絶対収益の拡大が課題です。既観測期間の**固定グリッド事後評価**ではSharpe 2超・年率5%超の候補もありましたが、これは学習期間だけで選択したWFや独立OOSの結果とは区別しています。

戦略別の用語は下記の研究総括で日本語の意味を併記しています。詳しい結果と限界は[Phase 1〜6.1研究総括](research/phase1_to_phase61_summary.md)を参照してください。

## 研究の進め方

1. **経済的根拠**：決算情報の段階的な株価反映、初動後のモメンタム・リバーサルを仮説化
2. **売買ルール**：シグナル観測時刻と発注可能時刻を区別し、保有期間、流動性、費用を設定
3. **最適化**：グリッド探索、近傍パラメータ、Top-K（上位K条件の組み合わせ）、共分散縮小、動的アンサンブル
4. **資金・リスク管理**：銘柄別配分、最大建玉、信用コスト、回転率、最大ドローダウン
5. **検証**：時系列WF、選択バイアスの明示、今後の未観測OOS検証

## 再現性と公開方針

- 公表・利用可能時刻より前の情報を売買判断に使わない。
- **IS（学習期間内）／既観測WF／固定グリッド事後評価／独立OOS／実運用**を明確に区別する。
- Sharpeだけでなく、年率収益、最大DD、資金稼働率、約定件数、コストも併記する。
- APIキー、個人情報、勤務先の非公開情報、認証情報を公開しない。
- J-Quantsなどの利用許諾が必要な生データを無断で再配布しない。

## 注意

本プロジェクトは調査研究・過去シミュレーションです。投資助言や将来収益の保証を目的とするものではありません。

## 再実行手順

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

## Phase 3

同じPowerShell環境で `.venv/Scripts/python -m pead01.phase3` を実行する。入力はPhase 2のローカルParquetと同じ生データ。全シグナル、日次損益、約定台帳、OOS集計は `data/phase3/` に保存する。

入力が同じ場合は `--reuse-signals` で保存済みシグナルから再計算できる。集計結果を使ったレポートの再生成は `--reports-only`。

[結果](reports/phase3_findings.md) · [執行](reports/phase3_execution.md) · [ポートフォリオ](reports/phase3_portfolio.md) · [OOS](reports/phase3_oos.md) · [方法](docs/phase3_methodology.md)

## Phase 6 ローカルバッチ

```powershell
$env:PYTHONPATH = "src"
$env:OPENBLAS_NUM_THREADS = "1"
.venv/Scripts/python -m pead01.phase6 --mode report --adopt-existing --resume
.\scripts\Start-Phase6.ps1 -Workers 8 -MemoryMiB 4096
```

最初のコマンドは保存済み計算を取り込み、レポートだけを作る。ランチャーはWindowsの独立プロセスで再開する。個別段階は `--mode paths|search|ensemble|walkforward|report`。C/Dのチェックポイントは段階単位、探索は方式・保有期間単位。

停止は `New-Item data/phase6_v6/phase6.pause -ItemType File -Force`。停止を確認後に `Remove-Item -LiteralPath data/phase6_v6/phase6.pause` を実行して再起動する。進捗は `data/phase6_v6/phase6_progress.json`、詳細は同ディレクトリの `logs/`。メモリ設定は探索並列数を抑える目安で、OSによる強制上限は設定しない。[計算方法](docs/phase6_methodology.md)
