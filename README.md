# plasma_codesign

低圧 CCP / ICP+Bias 向けの **回路・波形・寄生配置の共設計** を始めるための、`ngspice` 中心の研究用たたき台です。

この一式は、次の考え方に沿ってあります。

- プラズマを **単なる時変インピーダンス** ではなく、**状態を持つ多端子 ROM** として扱う
- `ngspice` は **高速な装置回路評価器** として使う
- 将来 `COMSOL` に持ち込めるように、**portable な SPICE 回路** と **ngspice 専用 ROM** を分離する
- 目的関数は単なる波形一致ではなく、**電流ピーク・損失・自己バイアス・不確かさ** を含める

## 構成

```text
plasma_codesign/
  README.md
  requirements.txt
  ports/
    plasma_ports.yaml
  configs/
    design_space_ccp.yaml
    design_space_icp_bias.yaml
  templates/
    hardware_portable_ccp.cir.tmpl
    hardware_full_ccp_ngspice.cir.tmpl
    hardware_portable_icp_bias.cir.tmpl
    hardware_full_icp_bias_ngspice.cir.tmpl
  models/
    plasma_ccp_rom_fallback.inc
    plasma_icp_bias_rom_fallback.inc
  data/
    target_ccp_waveform.csv
    target_bias_waveform.csv
    example_plasma_ccp_reference.csv
    example_plasma_icp_bias_reference.csv
  scripts/
    common.py
    generate_targets.py
    fit_ccp_rom.py
    fit_icp_bias_rom.py
    optimizer.py
  results/
```

## 前提

- Python 3.10+
- `ngspice` は **外部でインストール** して使ってください
- Python 依存は `requirements.txt` に記載

```bash
python -m pip install -r requirements.txt
```

macOS (Homebrew) 例:

```bash
brew install ngspice
```

## 使い方の最短手順

### 1) まず target waveform を確認
例の target は既に `data/` に置いてあります。必要なら再生成できます。

```bash
python scripts/generate_targets.py --outdir data
```

### 2) CCP の ROM 初期値を plasma シミュレーション時系列から当てる
入力 CSV は最低でも `time,v_port,i_port` を持たせてください。

```bash
python scripts/fit_ccp_rom.py \
  --input data/example_plasma_ccp_reference.csv \
  --output results/fitted_ccp_params.yaml
```

### 3) ngspice で mixed optimization を回す
まずは CCP で。

```bash
python scripts/optimizer.py \
  --config configs/design_space_ccp.yaml \
  --workdir results/ccp_run \
  --ngspice ngspice
```

ICP+Bias は:

```bash
python scripts/optimizer.py \
  --config configs/design_space_icp_bias.yaml \
  --workdir results/icp_bias_run \
  --ngspice ngspice
```

### 4) COMSOL へ持っていく
`templates/hardware_portable_*.cir.tmpl` をレンダした `.cir` を使ってください。
`portable` 側は **SPICE import 用**、`full_ngspice` 側は **最適化・評価用** です。

## 重要な注意

1. `models/*.inc` は **研究用の smooth surrogate** です。  
   第一原理 PIC / fluid / COMSOL Plasma Module そのものではありません。

2. `fit_*.py` は **初期 ROM を得るための最小実装** です。  
   実運用では、pressure / gas mix / wall condition ごとに分けて学習してください。

3. `optimizer.py` は **混合離散連続のロバスト探索の最小版** です。  
   大規模化するなら Optuna / BoTorch / Nevergrad などへ置き換えてください。

4. `portable` テンプレートは **COMSOL import を意識して behavioral 要素を入れていません**。  
   一方 `full_ngspice` は `behavioral B source` と `Q=` capacitor を使います。

## 実験・高忠実度モデルとの接続

推奨フローは次です。

1. PIC / fluid / COMSOL から `v(t), i(t), q(t), self-bias, Pabs` を取得
2. `fit_*.py` で ROM 初期値を作る
3. `optimizer.py` で装置回路を広く探索
4. 上位候補だけ高忠実度モデルへ戻して再評価
5. 最後に `portable` 回路を COMSOL に持ち込んで幾何・場・回路を再確認

## 何を自分の系に合わせて変えるべきか

- `configs/design_space_*.yaml`
- `data/target_*.csv`
- `models/*.inc` の式
- `scripts/fit_*.py` の同定モデル
- `templates/*.cir.tmpl` の source / matching / return path / feedthrough


## 追加: synthetic benchmark dataset

このプロジェクトには、既存の ROM フィットコードと設計空間定義を使って作った **擬似ベンチマークデータセット** を追加してあります。

生成:
```bash
python scripts/generate_targets.py --outdir data
python scripts/generate_benchmark_dataset.py --repo-root . --out-root benchmark
python scripts/evaluate_identification_baselines.py --benchmark-root benchmark --outdir benchmark/baselines
```

主な成果物:
- `benchmark/manifest.json`
- `benchmark/ccp_identification/`
- `benchmark/icp_bias_identification/`
- `benchmark/ccp_codesign/`
- `benchmark/icp_bias_codesign/`
- `benchmark/baselines/`

## フル実行手順（同定 + 最適化 + 可視化）

```bash
python scripts/generate_targets.py --outdir data

python scripts/generate_benchmark_dataset.py --repo-root . --out-root benchmark
python scripts/evaluate_identification_baselines.py --benchmark-root benchmark --outdir benchmark/baselines

python scripts/optimizer.py --config configs/design_space_ccp.yaml --workdir results/ccp_run --ngspice ngspice
python scripts/optimizer.py --config configs/design_space_icp_bias.yaml --workdir results/icp_bias_run --ngspice ngspice

python scripts/plot_benchmark_insights.py --benchmark-root benchmark --outdir results/benchmark_figures
```

ワンコマンド実行（事前チェック付き）:

```bash
python scripts/run_benchmark_full.py --ngspice ngspice
```

## 追加: 可視化と考察用グラフ出力

ベンチマーク内容の考察用に、次を一括で図化できます。

- CCP / ICP+Bias の回路ブロック図 + 代表波形
- ロバスト最適化（mean / std / robust）のトレードオフ
- 上位設計のロバスト目的分解
- case レベルの `v_rmse` vs `i_peak` 比較
- scenario 別目的関数分布
- 同定ベースラインの split 比較
- ID / OOD ギャップ比較

```bash
python scripts/plot_benchmark_insights.py \
  --benchmark-root benchmark \
  --outdir results/benchmark_figures
```

主な出力:
- `results/benchmark_figures/ccp_circuit_and_waveform.png`
- `results/benchmark_figures/icp_bias_circuit_and_waveform.png`
- `results/benchmark_figures/robust_tradeoff_scatter.png`
- `results/benchmark_figures/top_design_decomposition.png`
- `results/benchmark_figures/case_pareto_vrmse_ipeak.png`
- `results/benchmark_figures/scenario_objective_distribution.png`
- `results/benchmark_figures/identification_baseline_comparison.png`
- `results/benchmark_figures/id_vs_ood_gap.png`
- `results/benchmark_figures/INSIGHT_SUMMARY.md`

さらに詳細な比較・評価（ECDF, ID/OOD CI, Pareto front, 感度, 上位/中央値波形比較）は:

```bash
python scripts/plot_benchmark_deep_dive.py \
  --benchmark-root benchmark \
  --repo-root . \
  --outdir results/benchmark_figures
```

主な追加出力:
- `results/benchmark_figures/deep_ccp_schematic_schemdraw.svg`
- `results/benchmark_figures/deep_icp_bias_schematic_schemdraw.svg`
- `results/benchmark_figures/deep_smith_charts.png`
- `results/benchmark_figures/deep_impedance_plane.png`
- `results/benchmark_figures/deep_return_loss_distribution.png`
- `results/benchmark_figures/deep_baseline_ecdf.png`
- `results/benchmark_figures/deep_baseline_split_hist.png`
- `results/benchmark_figures/deep_id_ood_ci.png`
- `results/benchmark_figures/deep_pareto_frontier.png`
- `results/benchmark_figures/deep_robust_split_violin.png`
- `results/benchmark_figures/deep_topology_effect.png`
- `results/benchmark_figures/deep_stability_index.png`
- `results/benchmark_figures/deep_factor_correlation.png`
- `results/benchmark_figures/deep_scenario_uplift.png`
- `results/benchmark_figures/deep_waveform_top_vs_median.png`
- `results/benchmark_figures/deep_dive_stats.json`
- `results/benchmark_figures/DEEP_DIVE_SUMMARY.md`

最適化の進行と「指標ごとの最良回路 + 効果比較」をまとめて出すには:

```bash
python scripts/plot_optimizer_metric_story.py \
  --repo-root . \
  --ccp-workdir results/ccp_run \
  --icp-workdir results/icp_bias_run \
  --outdir results/optimizer_story
```

主な出力:
- `results/optimizer_story/ccp/optimizer_progress_ccp.png`
- `results/optimizer_story/ccp/optimizer_tradeoff_ccp.png`
- `results/optimizer_story/ccp/optimizer_ccp_*_schematic.png`
- `results/optimizer_story/ccp/optimizer_ccp_*_story.png`
- `results/optimizer_story/ccp/optimizer_metric_ratio_heatmap_ccp.png`
- `results/optimizer_story/ccp/optimizer_metric_effect_summary_ccp.png`
- `results/optimizer_story/icp_bias/optimizer_progress_icp_bias.png`
- `results/optimizer_story/icp_bias/optimizer_tradeoff_icp_bias.png`
- `results/optimizer_story/icp_bias/optimizer_icp_bias_*_schematic.png`
- `results/optimizer_story/icp_bias/optimizer_icp_bias_*_story.png`
- `results/optimizer_story/icp_bias/optimizer_metric_ratio_heatmap_icp_bias.png`
- `results/optimizer_story/icp_bias/optimizer_metric_effect_summary_icp_bias.png`
- `results/optimizer_story/optimizer_metric_ratio_heatmap_compare.png`
- `results/optimizer_story/*/optimizer_metric_winners_*.csv`
- `results/optimizer_story/*/optimizer_trials_*.csv`
