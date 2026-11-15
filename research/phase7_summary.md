# PEAD01 Phase 7 研究総括

Phase 6 日足統一版（58343a5）の864候補を再利用。Neighborの全期Sharpeは2.00、2025Q2を外すと0.75。同四半期の正寄与の上位10イベント比率は62.47%。上位10イベントの日次寄与を除いた全期Sharpeは1.17。

中央寄りのWF窓でのSharpe（既存選択を現金から再生 → 再選択）は126日 0.89 → 1.04、252日 3.26 → -0.19、504日 2.08 → -0.14。

多重比較調整後のp値は10日 0.215、40日 0.557。最高方式の指定は事後比較。実際の期初採用は学習・内部検証の情報で決定。独立OOSは未実施。

- [評価窓の感応度](../reports/phase7_wf_window_robustness.md)
- [2025Q2の利益分解](../reports/phase7_profit_concentration.md)
- [採用パラメータの持続性](../reports/phase7_parameter_persistence.md)
