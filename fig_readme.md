# Figure README

このファイルは、`results/benchmark_figures/` と `results/optimizer_story/` に出力される各グラフの意味と読み方をまとめたものです。

## 1. Benchmark Insights (`results/benchmark_figures`)

### `ccp_circuit_and_waveform.png`
- 上段: CCP 最良ロバスト設計の回路ブロック図。
- 下段: 代表ケースの `v_port`, `v_src`, `i_port` 波形。
- 読み方: 波形追従（電圧）と電流ストレス（電流）の同時確認に使う。

### `icp_bias_circuit_and_waveform.png`
- 上段: ICP+Bias 最良ロバスト設計の回路ブロック図。
- 中段: coil 側波形 (`v_coil`, `v_src_coil`, `i_coil`)。
- 下段: bias 側波形 (`v_bias`, `i_bias`)。
- 読み方: coil/bias の二系統を同時に見て、どちらが律速かを判定する。

### `robust_tradeoff_scatter.png`
- 横軸: `mean_objective`、縦軸: `std_objective`、色: `robust_objective`。
- 破線: `robust = mean + risk_weight * std` の等高線。
- 読み方: 低平均・低分散を同時に満たす設計領域を特定する。

### `top_design_decomposition.png`
- 上位ロバスト設計の `mean` 成分と `risk(std)` 成分の積み上げ分解。
- 読み方: 「平均性能が効いているのか」「分散ペナルティが効いているのか」を比較する。

### `case_pareto_vrmse_ipeak.png`
- 横軸: `v_rmse`、縦軸: `i_peak`、色: `objective`、マーカー: シナリオ。
- 読み方: 波形誤差と電流ピークのトレードオフ構造をケース単位で確認する。

### `scenario_objective_distribution.png`
- シナリオ別 (`nominal`, `shifted_surface`, `ood_nonlin`) の objective 分布を split 別に箱ひげ表示。
- 読み方: 難シナリオと split 依存性（train/val/test）を切り分ける。

### `identification_baseline_comparison.png`
- 同定ベースライン誤差（NRMSE）の split 比較。
- 左: CCP (`nrmse_meas`, `nrmse_clean`)。
- 右: ICP (`coil_nrmse_meas`, `bias_nrmse_meas`)。
- 読み方: どのポート・どの split で同定が崩れているかを特定する。

### `id_vs_ood_gap.png`
- ID と OOD の平均誤差比較（棒グラフ）。
- 読み方: 一般化ギャップの大きさをメトリクス単位で把握する。

---

## 2. Deep Dive (`results/benchmark_figures`)

### `deep_ccp_schematic_schemdraw.svg` / `deep_ccp_schematic_schemdraw.png`
- CCP 最良ロバスト設計を `schemdraw` で描画した回路図。
- 読み方: 実際に選ばれた素子値・トポロジを回路構造として確認する。

### `deep_icp_bias_schematic_schemdraw.svg` / `deep_icp_bias_schematic_schemdraw.png`
- ICP+Bias 最良ロバスト設計の回路図（coil branch / bias branch）。
- 読み方: 2系統のマッチング構成と共通プラズマ負荷の関係を確認する。

### `deep_smith_charts.png`
- 基本波インピーダンスを Smith chart 上にプロット。
- 左: CCP、右: ICP+Bias（bias port）。
- 読み方: 反射係数の分布とシナリオ差を高周波整合の観点で確認する。

### `deep_impedance_plane.png`
- 複素インピーダンス平面 (`Re{Z}`, `Im{Z}`) 上の散布図。
- 読み方: 抵抗成分/リアクタンス成分の偏りとシナリオごとの差を確認する。

### `deep_return_loss_distribution.png`
- シナリオ別 Return Loss 分布。
- 読み方: どのシナリオで整合が悪化するかを比較する。

### `deep_baseline_ecdf.png`
- 同定誤差の ECDF（累積分布）を split 別に表示。
- 読み方: 平均値だけでなく、分布全体の右裾（悪化ケース）を評価する。

### `deep_baseline_split_hist.png`
- CCP/ICP の代表誤差指標ヒストグラム（split 別、密度）。
- 読み方: split 間で分布形状がどう変わるかを視覚比較する。

### `deep_id_ood_ci.png`
- ID vs OOD の平均誤差 + 95% bootstrap CI。
- 読み方: 差の有無だけでなく不確かさ込みで有意性を判断する。

### `deep_pareto_frontier.png`
- `mean_objective` と `std_objective` の Pareto 前線。
- 読み方: 非支配解の数と形状から探索空間の難易度を把握する。

### `deep_robust_split_violin.png`
- split 別の `robust_objective` 分布（violin + box）。
- 読み方: split ごとのばらつきと中央値差を同時に評価する。

### `deep_topology_effect.png`
- トポロジ別 (`L` / `PI`) の `robust_objective` 分布。
- 左: CCP、中: ICP coil、右: ICP bias。
- 読み方: トポロジ選択が目的関数に与える影響を比較する。

### `deep_stability_index.png`
- 横軸: `mean_objective`、縦軸: `std/mean`（安定性比）、色: `robust_objective`。
- 読み方: 高性能だが不安定な設計と、安定だが性能が低い設計を分離する。

### `deep_factor_correlation.png`
- `robust_objective` に対する Spearman 相関上位因子。
- 読み方: 改善余地の大きい設計変数の優先順位付けに使う。

### `deep_scenario_uplift.png`
- `nominal` 比でのシナリオ objective 増分。
- 読み方: どのシナリオが性能劣化を主導しているかを確認する。

### `deep_waveform_top_vs_median.png`
- 上位設計 vs 中央設計の波形比較（CCP/ICP 各2図）。
- 読み方: 「上位化」で何が改善し、何が悪化するかを波形で解釈する。

### `deep_id_ood_ci_table.csv`
- `deep_id_ood_ci.png` の元テーブル（mean, ci_lo, ci_hi）。
- 使い方: 数値比較やレポート表作成に利用。

### `deep_dive_stats.json`
- Deep Dive の集計統計（RF 指標、Pareto 点数、相関上位など）。
- 使い方: 自動レポートや追加分析の入力に利用。

---

## 3. Optimizer Story (`results/optimizer_story`)

### 3.1 進行・トレードオフ図

#### `ccp/optimizer_progress_ccp.png`
- trial ごとの `aggregate_objective` 推移、目的分解、主要メトリクス推移。
- 読み方: random 探索と local 探索の寄与、および収束挙動を確認。

#### `icp_bias/optimizer_progress_icp_bias.png`
- 上記の ICP+Bias 版。

#### `ccp/optimizer_tradeoff_ccp.png`
- 主要メトリクス間散布図（色は `aggregate_objective`）。
- 読み方: どのメトリクス間で衝突（trade-off）が大きいかを確認。

#### `icp_bias/optimizer_tradeoff_icp_bias.png`
- 上記の ICP+Bias 版。

### 3.2 指標別「最良回路 + 効果ストーリー」

以下の 10 図（CCP）と 10 図（ICP+Bias）は同じ読み方です。
- `*_schematic.png`: その指標で最良 trial の回路図。
- `*_story.png`: 左に回路図、右に「winner/median 比」の効果棒グラフ。

#### CCP (5指標)
- `ccp/optimizer_ccp_aggregate_objective_schematic.png`
- `ccp/optimizer_ccp_aggregate_objective_story.png`
- `ccp/optimizer_ccp_v_rmse_schematic.png`
- `ccp/optimizer_ccp_v_rmse_story.png`
- `ccp/optimizer_ccp_i_peak_schematic.png`
- `ccp/optimizer_ccp_i_peak_story.png`
- `ccp/optimizer_ccp_avg_power_abs_schematic.png`
- `ccp/optimizer_ccp_avg_power_abs_story.png`
- `ccp/optimizer_ccp_selfbias_error_schematic.png`
- `ccp/optimizer_ccp_selfbias_error_story.png`

#### ICP+Bias (5指標)
- `icp_bias/optimizer_icp_bias_aggregate_objective_schematic.png`
- `icp_bias/optimizer_icp_bias_aggregate_objective_story.png`
- `icp_bias/optimizer_icp_bias_v_rmse_schematic.png`
- `icp_bias/optimizer_icp_bias_v_rmse_story.png`
- `icp_bias/optimizer_icp_bias_i_peak_schematic.png`
- `icp_bias/optimizer_icp_bias_i_peak_story.png`
- `icp_bias/optimizer_icp_bias_avg_power_abs_schematic.png`
- `icp_bias/optimizer_icp_bias_avg_power_abs_story.png`
- `icp_bias/optimizer_icp_bias_selfbias_error_schematic.png`
- `icp_bias/optimizer_icp_bias_selfbias_error_story.png`

### 3.3 指標間の相互作用まとめ

#### `ccp/optimizer_metric_ratio_heatmap_ccp.png`
- 行: 最適化した指標、列: 評価対象指標、セル値: `winner/median`。
- 読み方: 1.0 未満は改善、1.0 超は悪化。副作用の方向を俯瞰する。

#### `icp_bias/optimizer_metric_ratio_heatmap_icp_bias.png`
- 上記の ICP+Bias 版。

#### `ccp/optimizer_metric_effect_summary_ccp.png`
- 各「最適化指標」ごとの効果を棒で重ね表示した要約図。
- 読み方: どの最適化方針が全体としてバランス良いかを比較。

#### `icp_bias/optimizer_metric_effect_summary_icp_bias.png`
- 上記の ICP+Bias 版。

#### `optimizer_metric_ratio_heatmap_compare.png`
- CCP と ICP+Bias を横並びで比較するヒートマップ。
- 読み方: 同じ指標最適化でも問題設定で副作用構造がどう違うかを比較。

### 3.4 集計CSV

#### `ccp/optimizer_metric_winners_ccp.csv`
- 指標ごとの winner trial と、全指標に対する `ratio_vs_median__*` を格納。

#### `icp_bias/optimizer_metric_winners_icp_bias.csv`
- 上記の ICP+Bias 版。

#### `ccp/optimizer_trials_ccp.csv`
- 全 trial の時系列テーブル（phase、objective、設計値など）。

#### `icp_bias/optimizer_trials_icp_bias.csv`
- 上記の ICP+Bias 版。

---

## 4. 表示上の注意

- `optimizer_metric_ratio_heatmap_*` / `optimizer_metric_effect_summary_*` は、可読性のため表示値を `0.2x - 10x` にクリップしています。
- 生の比率値は `optimizer_metric_winners_*.csv` に保存されています。
- RF 指標（Smith/Return Loss）は時間波形の基本波フェーザから算出した近似評価です。

---

## 5. 再生成コマンド

```bash
./.venv/bin/python scripts/plot_benchmark_insights.py --benchmark-root benchmark --outdir results/benchmark_figures
./.venv/bin/python scripts/plot_benchmark_deep_dive.py --benchmark-root benchmark --repo-root . --outdir results/benchmark_figures
./.venv/bin/python scripts/plot_optimizer_metric_story.py --repo-root . --ccp-workdir results/ccp_run --icp-workdir results/icp_bias_run --outdir results/optimizer_story
```
