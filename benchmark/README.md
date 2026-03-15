# plasma_codesign synthetic benchmark

このベンチマークは、低圧プラズマを**時変インピーダンス1個**ではなく、**状態を持つ差動ポート負荷**として扱う回路・波形・寄生配置の共設計を意識して作った**擬似データ**です。

## 何が入っているか

- `ccp_identification/`
  - 1ポート CCP の **同定用時系列ケース**
  - 既存の `scripts/fit_ccp_rom.py` にそのまま与えられる `time,v_port,i_port` を含む CSV
- `icp_bias_identification/`
  - 2ポート ICP+Bias の **同定用時系列ケース**
  - 既存の `scripts/fit_icp_bias_rom.py` にそのまま与えられる `time,v_coil,i_coil,v_bias,i_bias` を含む CSV
- `ccp_codesign/`
  - 回路設計値、運転条件、プラズマ不確かさシナリオ、目的関数、代理プロセス指標をまとめた表
  - 波形は `ccp_traces.csv.gz`
- `icp_bias_codesign/`
  - ICP+Bias の設計ベンチマーク表と圧縮時系列

## 研究的に意識した点

- **同定** と **設計最適化** を別タスクに分けている
- nominal / shifted_surface / ood_nonlin のように **分布外条件** を含めている
- 設計ベンチマークは **nominal design × 複数 uncertainty scenario** の形で、ロバスト最適化を直接試せる
- 真の時系列は、既存の ROM と同じ形をベースにしつつ、追加の memory / asymmetry / cross-coupling 項を足してあり、**完全な自己一致にはしていない**

## 注意

- これは**擬似ベンチマーク**であり、実験データや第一原理 PIC/流体の置き換えではありません
- `truth__*` の列は、隠れた真値パラメータの追跡用です
- `metric__` や summary CSV のプロセス指標は、設計用の**proxy**です
