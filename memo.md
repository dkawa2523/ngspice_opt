# Benchmark Result Memo (Detailed)

- Date: 2026-03-16
- Repository: `plasma_codesign_bench2 2`
- Benchmark dataset: `benchmark/`
- Figure output: `results/benchmark_figures/`, `results/optimizer_story/`

## 1. ライブラリ調査と採用方針

今回の要件（回路図をライブラリで描画、スミスチャート追加）に対して以下を比較し、採用した。

- 採用
  - `schemdraw`
    - Python で電子回路図を記号ベースで描画でき、SVG/PNG 出力が容易。
    - ベンチマークの最適設計パラメータを直接ラベル化しやすい。
  - `scikit-rf`
    - RF解析向けに Smith chart 描画・反射係数などの可視化と親和性が高い。
    - time-domain 波形から抽出した基本波インピーダンス点を直接投影できる。

- 比較候補
  - `PySpice`: シミュレーション統合には有用だが、図作成自体は主目的ではない。
  - `Lcapy`: 記号回路解析に強いが、今回の可視化目的では `schemdraw` の方が軽量。

- 非採用
  - `ChemDraw`
    - 化学構造式向けツールであり、電子回路図用途には適さない。

## 2. 実行範囲

本番条件（デフォルト件数）で以下を再実行済み。

1. `generate_targets.py`
2. `generate_benchmark_dataset.py`
3. `evaluate_identification_baselines.py`
4. `optimizer.py`（CCP / ICP+Bias）
5. `plot_benchmark_insights.py`
6. `plot_benchmark_deep_dive.py`（今回拡張版）
7. `plot_optimizer_metric_story.py`（今回追加）

## 3. データ規模

- CCP identification: 96
- ICP+Bias identification: 80
- CCP codesign: 80 designs x 4 scenarios = 320 cases
- ICP+Bias codesign: 64 designs x 4 scenarios = 256 cases

参照: `benchmark/manifest.json`

## 4. 追加した出力（回路図 / Smith / RF解釈）

### 4.1 回路図（ライブラリ描画）

- `deep_ccp_schematic_schemdraw.svg`
- `deep_icp_bias_schematic_schemdraw.svg`

内容:

- 最良ロバスト設計（CCP/ICP）の素子構成を `schemdraw` で描画。
- `R/L/C`, source 条件、matching 値を図中に埋め込み。

### 4.2 Smith chart と RF解釈グラフ

- `deep_smith_charts.png`
  - CCP と ICP(bias port) の基本波インピーダンス点を Smith chart 上に投影。
- `deep_impedance_plane.png`
  - `Re{Z}`–`Im{Z}` 平面で scenario ごとの差を可視化。
- `deep_return_loss_distribution.png`
  - scenario 別 Return Loss 分布を比較。

実装メモ:

- time-domain の `v(t), i(t)` から基本波複素フェーザを抽出し、`Z = V1 / I1` を計算。
- `Gamma = (Z/Z0 - 1) / (Z/Z0 + 1)`, `Z0 = 50Ω` で Smith chart へ投影。

## 5. 比較・評価結果（定量）

### 5.1 同定ベースライン（主要指標）

参照: `benchmark/baselines/baseline_summary.json`

- CCP overall
  - `nrmse_meas`: 0.0828
  - `nrmse_clean`: 0.0819
- ICP+Bias overall
  - `coil_nrmse_meas`: 0.0168
  - `bias_nrmse_meas`: 0.1437

split別（代表）:

- CCP `nrmse_meas`: train 0.0674, val 0.1344, test_id 0.1018, test_ood 0.0896
- ICP `bias_nrmse_meas`: train 0.1188, val 0.1918, test_id 0.1130, test_ood 0.2366

評価:

- ICP bias 側で OOD 劣化が顕著。
- CCP は OOD 一辺倒ではなく `val` の厳しさが支配。

### 5.2 ID/OOD 比較（95% bootstrap CI）

参照: `deep_id_ood_ci.png`, `deep_id_ood_ci_table.csv`

- CCP `nrmse_meas`
  - ID: 0.0819 [0.0573, 0.1125]
  - OOD: 0.0896 [0.0405, 0.1516]
- ICP `coil_nrmse_meas`
  - ID: 0.0116 [0.0098, 0.0145]
  - OOD: 0.0535 [0.0194, 0.1170]
- ICP `bias_nrmse_meas`
  - ID: 0.1305 [0.1053, 0.1684]
  - OOD: 0.2366 [0.1487, 0.3597]

評価:

- ICP の OOD 劣化は明確（coil 約4.6x、bias 約1.8x）。
- CCP は CI が重なり、ID/OOD差より split 混在難易度が効いている。

### 5.3 ロバスト設計分布・Pareto

参照: `deep_pareto_frontier.png`, `deep_robust_split_violin.png`, `deep_dive_stats.json`

Pareto前線点数（min mean / min std）:

- CCP: 3
- ICP+Bias: 6

`robust_objective` 分布:

- CCP: q10 35.998, q50 84.982, q90 185.008, best 17.133, worst 222.419
- ICP+Bias: q10 80.716, q50 124.249, q90 184.693, best 41.635, worst 240.504

split別 robust 平均:

- CCP: val 91.06, train 104.87, test_id 106.25
- ICP+Bias: train 127.10, test_id 127.61, val 140.39

### 5.4 上位設計の分離度

- CCP robust
  - best: 17.133
  - second: 24.669
  - gap: 7.535（約1.44x）
- ICP robust
  - best: 41.635
  - second: 61.455
  - gap: 19.820（約1.48x）

評価:

- どちらも最良設計が2位から十分に分離している。

### 5.5 トポロジー影響

参照: `deep_topology_effect.png`

トポロジー別 robust 平均:

- CCP: `L=96.28`, `PI=109.47`
- ICP coil: `L=129.29`, `PI=130.11`
- ICP bias: `L=125.36`, `PI=136.89`

評価:

- CCP は平均的に L 優位。
- ICP は coil 差は小、bias は L 優位。

### 5.6 安定性指標（std/mean）

参照: `deep_stability_index.png`

- CCP: median 0.0329, q90 0.1284
- ICP+Bias: median 0.0148, q90 0.0329

評価:

- ICP は相対変動が小さく安定。
- CCP は設計次第で不確かさ感度のばらつきが大きい。

### 5.7 Scenario 感度（nominal 比）

参照: `deep_scenario_uplift.png`

- CCP uplift: shifted_surface +1.662, ood_nonlin +3.433
- ICP uplift: shifted_surface +0.507, ood_nonlin -0.331

評価:

- CCP は `ood_nonlin` が最難。
- ICP は `shifted_surface` のほうが厳しい。

### 5.8 RF整合指標（Smith/Return Loss 由来）

参照: `deep_smith_charts.png`, `deep_return_loss_distribution.png`, `deep_dive_stats.json`

平均指標:

- CCP
  - `|Gamma| mean`: 0.9965
  - `return_loss_mean_db`: 0.031 dB
- ICP bias port
  - `|Gamma| mean`: 0.9858
  - `return_loss_mean_db`: 0.139 dB

scenario別平均 Return Loss (dB):

- CCP: nominal 0.030, shifted_surface 0.029, ood_nonlin 0.035
- ICP: nominal 0.131, shifted_surface 0.156, ood_nonlin 0.140

解釈:

- 全体的に整合は非常に悪い（|Gamma| が 1 に近い）。
- 本データは擬似生成で能動的な振る舞いを含むため、一部点で |Gamma|>1 が発生し得る。
- 実測/受動系評価ではこの点を別途マスクし、受動性制約付きで再評価するのが妥当。

### 5.9 上位 vs 中央値の波形比較

参照: `deep_waveform_top_vs_median.png`

対象:

- CCP: best `ccp_design_002` vs median `ccp_design_044`
- ICP: best `icp_design_001` vs median `icp_design_053`

target RMSE（nominal代表ケース）:

- CCP `v_port`: best 14.57, median 72.59
- ICP `v_bias`: best 40.91, median 124.46

評価:

- 上位設計は target 追従で明確に改善。
- 電流ストレスは単調に減らないため、波形追従とストレスの同時最適化が必要。

### 5.10 最適化指標ごとの回路図と効果まとめ（今回追加）

参照:

- `results/optimizer_story/ccp/optimizer_progress_ccp.png`
- `results/optimizer_story/icp_bias/optimizer_progress_icp_bias.png`
- `results/optimizer_story/ccp/optimizer_tradeoff_ccp.png`
- `results/optimizer_story/icp_bias/optimizer_tradeoff_icp_bias.png`
- `results/optimizer_story/ccp/optimizer_ccp_*_schematic.png`
- `results/optimizer_story/ccp/optimizer_ccp_*_story.png`
- `results/optimizer_story/icp_bias/optimizer_icp_bias_*_schematic.png`
- `results/optimizer_story/icp_bias/optimizer_icp_bias_*_story.png`
- `results/optimizer_story/ccp/optimizer_metric_ratio_heatmap_ccp.png`
- `results/optimizer_story/icp_bias/optimizer_metric_ratio_heatmap_icp_bias.png`
- `results/optimizer_story/ccp/optimizer_metric_effect_summary_ccp.png`
- `results/optimizer_story/icp_bias/optimizer_metric_effect_summary_icp_bias.png`
- `results/optimizer_story/optimizer_metric_ratio_heatmap_compare.png`
- `results/optimizer_story/ccp/optimizer_metric_winners_ccp.csv`
- `results/optimizer_story/icp_bias/optimizer_metric_winners_icp_bias.csv`

出力意図:

- 各最適化指標（`aggregate_objective`, `v_rmse`, `i_peak`, `avg_power_abs`, `selfbias_error`）について:
  - その指標で最良となった trial の回路図を出力
  - 同時に、他指標への副作用を「中央値 trial 比」で可視化
- さらに、熱マップと棒グラフで「指標最適化の相互作用」を比較可能にした。

CCP の読み取り（`optimizer_metric_winners_ccp.csv`）:

- aggregate objective 最良: trial 40（local）, objective 111.37
- `i_peak` と `avg_power_abs` の最良は同じ trial 32（local）
- trial1 から最良までの `aggregate_objective` 改善率: 約14.10%
- ランダム探索平均 115.73 に対して local 探索平均 112.01 で改善
- 副作用:
  - `v_rmse` 最適化では `avg_power_abs` が中央値比で最大 7.50x 悪化
  - `i_peak` 最適化では主要指標の多くが 1.0x 以下で、比較的バランス良好

ICP+Bias の読み取り（`optimizer_metric_winners_icp_bias.csv`）:

- aggregate objective 最良: trial 24（local）, objective 52.4047
- trial1 から最良までの `aggregate_objective` 改善率: 約0.023%（改善余地が小さい）
- `selfbias_error` 単独最適化は trial 3（random）で、objective は 86.09 と悪化
- 副作用:
  - `selfbias_error` 最適化は `avg_power_abs` の大幅悪化を伴う
  - `aggregate_objective` / `i_peak` 最適化は同 trial に収束し、現設定では同じ設計が優位

実装上の注意:

- `avg_power_abs` は中央値が極小になるケースがあるため、図の表示は `0.2x-10x` でクリップ。
- 生値は CSV（`optimizer_metric_winners_*.csv`）に保持し、再解析時に制限なしで参照可能。

## 6. 総合結論

- 本ベンチマークは、同定と設計最適化を scenario とロバスト指標で比較可能にしている。
- 現状の支配課題は ICP bias の一般化（特に OOD）。
- 設計探索では CCP は利得も分散も大きく、ICP は比較的安定だが bias 条件依存が強い。
- RF観点では整合性が全般に低く、受動性制約を意識した再設計が次の論点。
- 指標別ストーリー図から、CCP は「電流/電力最適化が比較的整合的」、ICP+Bias は「自己バイアス最適化が他指標と衝突しやすい」ことが確認できた。

## 7. 次アクション提案

1. ICP bias 同定強化（履歴/高調波特徴の追加）
2. split/シナリオ設計の再定義（CCP val難化要因の切り分け）
3. `robust = mean + lambda*std` の lambda スイープ
4. RF制約追加（|Gamma|, RL, VSWR, 受動性）
5. 上位設計の高忠実度再評価（rank consistency）
6. ICP+Bias の `target_selfbias`/重み `w_selfbias` 再設定と再探索（目的間衝突の緩和）

## 8. 参照ファイル

- `benchmark/manifest.json`
- `benchmark/baselines/baseline_summary.json`
- `results/benchmark_figures/INSIGHT_SUMMARY.md`
- `results/benchmark_figures/DEEP_DIVE_SUMMARY.md`
- `results/benchmark_figures/deep_dive_stats.json`
- `results/optimizer_story/ccp/optimizer_metric_winners_ccp.csv`
- `results/optimizer_story/icp_bias/optimizer_metric_winners_icp_bias.csv`
- `results/optimizer_story/optimizer_metric_ratio_heatmap_compare.png`
