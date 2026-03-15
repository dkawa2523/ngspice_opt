# 低圧プラズマ共設計ベンチマーク 本番実行レポート

- 実行日: 2026-03-16 (JST)
- 実行環境: Python 3.10.8, ngspice-45.2
- 対象リポジトリ: `plasma_codesign_bench2 2`
- 実行コマンド:

```bash
./.venv/bin/python scripts/run_benchmark_full.py --python ./.venv/bin/python --ngspice ngspice
./.venv/bin/python scripts/plot_optimizer_metric_story.py --repo-root . --ccp-workdir results/ccp_run --icp-workdir results/icp_bias_run --outdir results/optimizer_story
```

---

## 1. 問題設定（低圧プラズマ・回路共設計）

本ベンチマークの問題は、低圧 CCP / ICP+Bias 装置において、以下を同時に満たす回路設計を見つけることである。

1. ターゲット波形への追従（特にバイアス電圧波形）
2. ピーク電流ストレスの抑制（素子・電源保護）
3. 吸収電力／自己バイアスの制御
4. プラズマパラメータ不確かさ下でのロバスト性

回路側は、マッチング回路トポロジ（`L` / `PI`）、L/C 値、配線寄生成分（ケーブル・リターン・フィード）を最適化対象とし、プラズマ側は ROM（状態を持つ surrogate）で表現して ngspice と結合する。

---

## 2. 課題（本問題が難しい理由）

### 2.1 物理課題（低圧プラズマ）
- プラズマ負荷は強非線形で、動作点依存・履歴依存を持つ。
- 同じ設計でもシナリオ（`nominal`, `shifted_surface`, `ood_nonlin`）で応答が変わる。
- ICP+Bias では coil 側と bias 側が同一プラズマ状態を介して結合し、片側最適化が他方に悪影響を与えやすい。

### 2.2 回路設計課題
- 波形誤差低減と電流ストレス低減はしばしばトレードオフ。
- 寄生成分（配線長、分布定数）を含むため、局所最適で破綻しやすい。
- RF 観点では整合不良（反射係数大）な候補が残ると、実装時に効率が出ない。

---

## 3. 目的

1. ベンチマーク（同定 + 共設計 + 可視化）を本番条件で完走させる。  
2. 精度・一般化・ロバスト性・回路解釈を同時に評価する。  
3. 「どの最適化指標を優先すると何が改善/悪化するか」を可視化し、実機設計に使える示唆を得る。

---

## 4. 方法

### 4.1 パイプライン

1. ターゲット波形生成 (`generate_targets.py`)
2. synthetic benchmark 生成 (`generate_benchmark_dataset.py`)
3. 同定ベースライン評価 (`evaluate_identification_baselines.py`)
4. ngspice 連携最適化 (`optimizer.py` for CCP / ICP+Bias)
5. 可視化 (`plot_benchmark_insights.py`, `plot_benchmark_deep_dive.py`, `plot_optimizer_metric_story.py`)

### 4.2 目的関数

各試行の基本 objective は以下（CCP/ICP 同型）:

- `objective = w_v * v_rmse + w_i * peak_penalty(i_peak) + w_p * |avg_power|/100 + w_sb * |selfbias - target_selfbias|/100`
- `peak_penalty(r)` は `r = i_peak / max_peak_current` に対して:
  - `r <= 1`: `0.05 * r`
  - `r > 1`: `0.05 + (r - 1)^2`

不確かさサンプル `n_uncertainty = 4` に対し、

- `aggregate_objective = mean(objective) + risk_aversion_std * std(objective)`
- `risk_aversion_std = 0.35`

を最小化する。

### 4.3 探索設定

- CCP: `n_random=24`, `n_local=16`（計40 trial）
- ICP+Bias: `n_random=20`, `n_local=14`（計34 trial）
- 局所探索摂動: `local_sigma_fraction=0.15`

### 4.4 データ規模

`benchmark/manifest.json` より:

- CCP identification: 96 cases
- ICP+Bias identification: 80 cases
- CCP codesign: 80 designs × 4 scenarios = 320 cases
- ICP+Bias codesign: 64 designs × 4 scenarios = 256 cases

---

## 5. 結果

### 5.1 本番ベンチマーク再実行ステータス

- フルパイプライン完走: **成功**
- 出力更新:
  - `results/benchmark_figures`: insights 9件 + deep-dive 20件
  - `results/optimizer_story`: 33件

### 5.2 同定ベースライン（一般化性能）

`benchmark/baselines/baseline_summary.json` および `deep_id_ood_ci_table.csv` より:

### CCP

| 指標 | train | val | test_id | test_ood | overall |
|---|---:|---:|---:|---:|---:|
| nrmse_meas | 0.0674 | 0.1344 | 0.1018 | 0.0896 | 0.0828 |
| nrmse_clean | 0.0663 | 0.1344 | 0.1018 | 0.0876 | 0.0819 |

ID/OOD (95% CI):
- ID `nrmse_meas`: 0.0819 [0.0573, 0.1125]
- OOD `nrmse_meas`: 0.0896 [0.0405, 0.1516]

### ICP+Bias

| 指標 | train | val | test_id | test_ood | overall |
|---|---:|---:|---:|---:|---:|
| coil_nrmse_meas | 0.0103 | 0.0175 | 0.0104 | 0.0535 | 0.0168 |
| bias_nrmse_meas | 0.1188 | 0.1918 | 0.1130 | 0.2366 | 0.1437 |

ID/OOD (95% CI):
- coil: ID 0.0116 [0.0098, 0.0145] -> OOD 0.0535 [0.0194, 0.1170]（約4.6x）
- bias: ID 0.1305 [0.1053, 0.1684] -> OOD 0.2366 [0.1487, 0.3597]（約1.8x）

**所見**: ICP の OOD 劣化が主要課題。特に bias port 同定の一般化改善が必要。

### 5.3 最適化（ngspice 実行）

`results/*_run/history.json`, `best_result.json` より:

### CCP 最適化
- best trial: 40 (local)
- best aggregate objective: **111.3728**
- first trial からの改善率: **14.10%**
- random 平均: 115.7269
- local 平均: 112.0123

best mean metrics:
- objective: 111.3375
- v_rmse: 110.7722
- i_peak: 145.9036 A
- avg_power: 1.12e-06
- selfbias: 3.38e-07 V

best design（抜粋）:
- topology=PI
- VAC_BIAS=217.07 V
- L_MATCH=3.38e-07 H
- C_MATCH_IN=7.64e-10 F
- C_MATCH_OUT=2.06e-11 F
- C_BLOCK=5.30e-10 F
- CABLE_LEN_M=3.30 m
- RETURN_LEN_M=0.446 m

### ICP+Bias 最適化
- best trial: 24 (local)
- best aggregate objective: **52.4047**
- first trial からの改善率: **0.0235%**（初期点でほぼ収束域）
- random 平均: 68.6920
- local 平均: 59.3242

best mean metrics:
- objective: 52.4047
- v_rmse: 52.3445
- i_peak: 3.2800 A
- avg_power: -5.31e-15
- selfbias: 1.61e-15 V（target -50 Vから大きく乖離）

best design（抜粋）:
- coil_topology=PI, bias_topology=PI
- VICP_AC=158.73 V, VBIAS_AC=246.57 V, VBIAS_DC=-5.38 V
- L_COIL_MATCH=1.15e-06 H
- L_BIAS_MATCH=6.43e-08 H
- C_COIL_MATCH_OUT=1.04e-09 F
- C_BIAS_MATCH_OUT=4.27e-10 F
- C_BLOCK_BIAS=6.55e-10 F

**所見**:
- CCP は探索により継続改善。
- ICP+Bias は objective landscape が平坦/拘束的で、`selfbias` 目標達成が設計空間内で困難な兆候。

### 5.4 ベンチマーク設計集合（deep-dive統計）

`results/benchmark_figures/deep_dive_stats.json` より:

- Pareto 前線点数: CCP 3, ICP+Bias 6
- robust 分布中央値: CCP 84.98, ICP+Bias 124.25
- top design:
  - CCP `ccp_design_002`, robust 17.133
  - ICP `icp_design_001`, robust 41.635
- topology 平均 robust:
  - CCP: `L=96.28`, `PI=109.47`（L優位）
  - ICP coil: `L=129.29`, `PI=130.11`（差小）
  - ICP bias: `L=125.36`, `PI=136.89`（L優位）
- stability ratio (std/mean) median:
  - CCP: 0.0329
  - ICP+Bias: 0.0148
- scenario uplift (nominal 比):
  - CCP: shifted_surface +1.662, ood_nonlin +3.433
  - ICP+Bias: shifted_surface +0.507, ood_nonlin -0.331

**所見**:
- CCP は scenario 感度が大きく、特に `ood_nonlin` が厳しい。
- ICP+Bias は相対的に安定だが、bias 条件依存が残る。

### 5.5 RF整合（Smith/Return Loss）

`deep_smith_charts.png`, `deep_return_loss_distribution.png`, `deep_dive_stats.json` より:

- CCP: `|Gamma| mean = 0.9965`, `RL mean = 0.031 dB`
- ICP+Bias(bias port): `|Gamma| mean = 0.9858`, `RL mean = 0.139 dB`

シナリオ別 RL 平均 (dB):
- CCP: nominal 0.030, shifted_surface 0.029, ood_nonlin 0.035
- ICP: nominal 0.131, shifted_surface 0.156, ood_nonlin 0.140

**所見**:
- 全体として整合は非常に悪い（|Gamma| ≈ 1）。
- 現状は「波形追従主導」の設計が優先され、RF効率・反射抑制が未拘束。

### 5.6 最適化指標別ストーリー（副作用分析）

`results/optimizer_story/*` より:

### CCP
- `i_peak` 最適化（trial 32）は `i_peak` 0.389x, `avg_power_abs` 0.217x と大きく改善しつつ、`aggregate` も 0.993x。
- `v_rmse` 最適化（trial 12）は `avg_power_abs` 7.50x, `i_peak` 4.04x と副作用が大きい。

### ICP+Bias
- `aggregate_objective` 最適と `i_peak` 最適が同一 trial（24）に一致。
- `selfbias_error` 最適化（trial 3）は `aggregate` 1.64x 悪化、`i_peak` 10.28x 悪化。
- `avg_power_abs` 比が極端に見える箇所は分母が極小なため（可視化は 0.2x-10x クリップ）。

**所見**:
- CCP は「電流/電力優先」が総合的にも有利。
- ICP+Bias は自己バイアス単独最適化が他目的と強く衝突。

---

## 6. 結果考察（低圧プラズマ専門家 + 回路設計者の視点）

### 6.1 物理モデル観点

1. **ICP bias 側一般化の脆弱性**  
   OOD で bias 誤差が増大しており、ROM が壁面条件/非線形容量変化を十分表現できていない。

2. **CCP のシナリオ感度**  
   `ood_nonlin` で objective uplift が最大。電極シースの非線形性（電圧依存容量・伝導変化）が支配的で、単一設定でのロバスト化が難しい。

3. **自己バイアス制御の構造的難しさ（ICP+Bias）**  
   最良解でも selfbias が 0 V 近傍に張り付くため、現設計空間・重み・拘束では `target_selfbias=-50V` を達成しにくい。

### 6.2 回路設計観点

1. **PI/L の使い分け**  
   データセット統計では CCP/ICP-bias ともに `L` 優位傾向。PI は自由度が高い反面、寄生成分込みで不安定方向へ触れやすい。

2. **電流ストレスと波形追従の競合**  
   `v_rmse` のみを追うと電流・電力が急増するケースが確認された。実機では素子定格・熱を先に満たす設計が必須。

3. **RF整合未拘束の影響**  
   |Gamma| が 1 近傍で、反射電力観点では不適。設計目的に RL/VSWR/受動性拘束を入れない限り、実機電源効率は改善しにくい。

### 6.3 実務上の結論

- 現ベンチマークは「最適化パイプラインの比較基盤」としては成立。  
- ただし「実機適用」を目指すには、次を同時に強化する必要がある。
  - ICP bias 同定の OOD 強化
  - 自己バイアス達成可能性を担保する設計空間再設計
  - RF整合拘束の導入

---

## 7. 残課題と改善提案（優先度順）

1. **目的関数再設計（最優先）**
- `selfbias` をソフト項ではなく制約化（例: `|selfbias-target| <= tol`）
- RL/VSWR 拘束を追加（例: `|Gamma|<=0.5`）

2. **設計空間再定義（ICP+Bias）**
- `VBIAS_DC`, `L_BIAS_MATCH`, `C_BIAS_MATCH_*`, feed parasitic の範囲を実機データで再較正
- bias 系のみの局所探索強化ステージを追加

3. **同定モデル強化**
- OOD シナリオ追加、時系列特徴量追加、ポート相互作用項を増強
- split 設計（train/val/test_ood）を実運用条件に近づける

4. **探索アルゴリズム高度化**
- 現行 random+local を多目的 BO（Optuna/BoTorch）へ移行
- パレート前線を直接探索し、後段で重み選定

5. **高忠実度検証ループ**
- 上位候補を PIC/fluid/COMSOL へ戻して順位整合（rank consistency）を評価

---

## 8. 参照ファイル（今回実行で更新）

- `benchmark/manifest.json`
- `benchmark/baselines/baseline_summary.json`
- `results/ccp_run/history.json`
- `results/ccp_run/best_result.json`
- `results/icp_bias_run/history.json`
- `results/icp_bias_run/best_result.json`
- `results/benchmark_figures/INSIGHT_SUMMARY.md`
- `results/benchmark_figures/DEEP_DIVE_SUMMARY.md`
- `results/benchmark_figures/deep_dive_stats.json`
- `results/benchmark_figures/deep_id_ood_ci_table.csv`
- `results/optimizer_story/ccp/optimizer_metric_winners_ccp.csv`
- `results/optimizer_story/icp_bias/optimizer_metric_winners_icp_bias.csv`
- `fig_readme.md`
