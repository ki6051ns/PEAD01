# PEAD01 Phase 7 研究総括

## 1. 研究目的・データ・評価期間

Phase 6の日足統一版864候補を用い、2024-10-01〜2026-11-13の516営業日における156方式を検証した。
採用履歴と価格経路を固定した台帳再生で日次の純損益・費用・約定・資金稼働率等を照合した。
Phase 6は候補構築とWF評価、Phase 7は統計分解と頑健性評価を扱う。独立OOSは未実施。

## 2. 初動方式別の統計

平均日数加重の設定配分が最も大きい初動方式はOpen→Openで42.67%。
設定配分と実際の約定・損益寄与は指標を分けて集計した。 [初動方式と保有期間の詳細](../reports/phase7/phase7_method_horizon_breakdown.md)

## 3. 保有期間別の統計

設定配分が最も大きい計画保有は10営業日（24.93%）。平均純寄与が最大の区分は30営業日（1.69%）。
各方式内の候補は共通資金を使うため、この寄与から保有期間単独の期待収益は推定できない。 [保有期間の詳細](../reports/phase7/phase7_method_horizon_breakdown.md#保有期間)

## 4. アンサンブル方式別の統計

全156設定のSharpe中央値は0.43。系列内中央値が最も高かったのはblank_dynamicの1.02（4設定）。
設定数は系列により異なる。 [方式比較](../reports/phase7/phase7_ensemble_comparison.md)

## 5. 月次・四半期・年次のWF成績

方式間の暦年累積中央値は2024年 0.74%、2025年 2.45%、2026年 -0.04%。2024年・2026年は観測端の部分年を含む。
最高方式Neighborの2025Q2は13.38%。各粒度の再複利を日次NAVと照合した。 [期間別成績](../reports/phase7/phase7_monthly_quarterly_yearly.md)

## 6. 2025Q2の収益集中

Neighborの全期Sharpeは2.00、2025Q2を除くと0.75。
同四半期の正寄与の上位10イベント比率は62.47%で、156方式の中央値は31.37%。
同四半期の上位10イベントの日次寄与を除いた全期Sharpeは1.17。 [全方式の帰属](../reports/phase7/phase7_event_profit_attribution.md) · [既存の詳細分解](../reports/phase7/phase7_profit_concentration.md)

## 7. パラメータ持続性・WF期間感応度

Neighborの隣接WF更新期のJaccardは平均5.95%。中央寄りの評価窓で、既存選択を現金から再生したSharpeと再選択のSharpeは126日で0.89 → 1.04、252日で3.26 → −0.19、504日で2.08 → −0.14。
再選択により更新日と採用候補が同時に変わる。 [期間感応度](../reports/phase7/phase7_wf_window_robustness.md) · [パラメータ持続性](../reports/phase7/phase7_parameter_persistence.md)

## 8. 統計的有意性・選択バイアス

最高方式の156方式多重比較調整済みp値は10日ブロックで0.215、40日で0.557。
最高方式は事後比較。期初採用は学習・内部検証で決定。重複窓と方式は互いに依存する。 [既存の統計検証](../reports/phase7/phase7_parameter_persistence.md)

## 9. 結論と残課題

高い観測Sharpeは収益集中と更新日の影響を受ける。初動・保有の帰属は共通資金台帳での記述分解で、各設定の効果を単独で識別していない。
事前に凍結した選択規則の未観測期間評価と、取引容量の確認が残る。

[Phase 7の方法・実装・再現](../docs/phase7/methodology.md) · [Phase 6日足統一版](phase6_daily_rebuild_summary.md) · [研究全体の索引](README.md)
