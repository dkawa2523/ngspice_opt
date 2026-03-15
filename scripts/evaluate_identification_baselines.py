
#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from common import load_csv_numeric, save_json
from fit_ccp_rom import simulate_ccp_port_model
from fit_icp_bias_rom import simulate_icp_bias_port_model


def fit_ccp_case(path: Path) -> dict:
    header, data = load_csv_numeric(path)
    idx = {n: i for i, n in enumerate(header)}
    t = data[:, idx["time"]]
    v = data[:, idx["v_port"]]
    i = data[:, idx["i_port"]]
    i_clean = data[:, idx["i_port_clean"]] if "i_port_clean" in idx else i

    x0 = np.array([2.0e-3, 0.20, 3.0e-11, 1.0e-11, 80.0, 8.0e-2, 4.0e-7], dtype=float)
    lb = np.array([1e-6, 0.0, 1e-13, 1e-13, 5.0, 1e-6, 1e-9], dtype=float)
    ub = np.array([1e-1, 3.0, 1e-8, 1e-8, 500.0, 5.0, 1e-3], dtype=float)

    def residual(x):
        pred = simulate_ccp_port_model(t, v, x)
        scale = max(np.max(np.abs(i)), 1e-9)
        return (pred - i) / scale

    res = least_squares(residual, x0=x0, bounds=(lb, ub), max_nfev=250)
    pred = simulate_ccp_port_model(t, v, res.x)
    rmse_meas = float(np.sqrt(np.mean((pred - i) ** 2)))
    nrmse_meas = rmse_meas / max(np.max(np.abs(i)), 1e-9)
    rmse_clean = float(np.sqrt(np.mean((pred - i_clean) ** 2)))
    nrmse_clean = rmse_clean / max(np.max(np.abs(i_clean)), 1e-9)
    return {
        "fit_success": bool(res.success),
        "cost": float(res.cost),
        "nrmse_meas": nrmse_meas,
        "nrmse_clean": nrmse_clean,
    }


def fit_icp_case(path: Path) -> dict:
    header, data = load_csv_numeric(path)
    idx = {n: i for i, n in enumerate(header)}
    t = data[:, idx["time"]]
    v_coil = data[:, idx["v_coil"]]
    i_coil = data[:, idx["i_coil"]]
    v_bias = data[:, idx["v_bias"]]
    i_bias = data[:, idx["i_bias"]]
    i_coil_clean = data[:, idx["i_coil_clean"]] if "i_coil_clean" in idx else i_coil
    i_bias_clean = data[:, idx["i_bias_clean"]] if "i_bias_clean" in idx else i_bias

    x0 = np.array([1e-3, 6e-4, 2e-6, 2e-3, 0.2, 3e-11, 1e-11, 80.0, 2e-3, 5e-2, 8e-7], dtype=float)
    lb = np.array([1e-6, 1e-7, 1e-8, 1e-6, 0.0, 1e-13, 1e-13, 5.0, 1e-6, 1e-6, 1e-9], dtype=float)
    ub = np.array([1e-1, 1e-1, 1e-3, 1e-1, 3.0, 1e-8, 1e-8, 500.0, 1.0, 1.0, 1e-3], dtype=float)

    def residual(x):
        pred_coil, pred_bias = simulate_icp_bias_port_model(t, v_coil, v_bias, x)
        s1 = max(np.max(np.abs(i_coil)), 1e-9)
        s2 = max(np.max(np.abs(i_bias)), 1e-9)
        return np.concatenate([(pred_coil - i_coil) / s1, (pred_bias - i_bias) / s2])

    res = least_squares(residual, x0=x0, bounds=(lb, ub), max_nfev=300)
    pred_coil, pred_bias = simulate_icp_bias_port_model(t, v_coil, v_bias, res.x)
    coil_nrmse_meas = float(np.sqrt(np.mean((pred_coil - i_coil) ** 2)) / max(np.max(np.abs(i_coil)), 1e-9))
    bias_nrmse_meas = float(np.sqrt(np.mean((pred_bias - i_bias) ** 2)) / max(np.max(np.abs(i_bias)), 1e-9))
    coil_nrmse_clean = float(np.sqrt(np.mean((pred_coil - i_coil_clean) ** 2)) / max(np.max(np.abs(i_coil_clean)), 1e-9))
    bias_nrmse_clean = float(np.sqrt(np.mean((pred_bias - i_bias_clean) ** 2)) / max(np.max(np.abs(i_bias_clean)), 1e-9))
    return {
        "fit_success": bool(res.success),
        "cost": float(res.cost),
        "coil_nrmse_meas": coil_nrmse_meas,
        "bias_nrmse_meas": bias_nrmse_meas,
        "coil_nrmse_clean": coil_nrmse_clean,
        "bias_nrmse_clean": bias_nrmse_clean,
    }


def summarize(df: pd.DataFrame, metric_cols: list[str]) -> dict:
    out = {}
    for split, g in df.groupby("split"):
        out[split] = {m: float(g[m].mean()) for m in metric_cols}
    out["overall"] = {m: float(df[m].mean()) for m in metric_cols}
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-root", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()

    outdir = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    ccp_index = pd.read_csv(args.benchmark_root / "ccp_identification" / "index.csv")
    ccp_rows = []
    for _, row in ccp_index.iterrows():
        metrics = fit_ccp_case(args.benchmark_root / row["file_path"])
        ccp_rows.append({"case_id": row["case_id"], "split": row["split"], **metrics})
    ccp_df = pd.DataFrame(ccp_rows)
    ccp_df.to_csv(outdir / "ccp_identification_baseline.csv", index=False)
    ccp_summary = summarize(ccp_df, ["nrmse_meas", "nrmse_clean", "cost"])

    icp_index = pd.read_csv(args.benchmark_root / "icp_bias_identification" / "index.csv")
    icp_rows = []
    for _, row in icp_index.iterrows():
        metrics = fit_icp_case(args.benchmark_root / row["file_path"])
        icp_rows.append({"case_id": row["case_id"], "split": row["split"], **metrics})
    icp_df = pd.DataFrame(icp_rows)
    icp_df.to_csv(outdir / "icp_identification_baseline.csv", index=False)
    icp_summary = summarize(icp_df, ["coil_nrmse_meas", "bias_nrmse_meas", "coil_nrmse_clean", "bias_nrmse_clean", "cost"])

    save_json({"ccp": ccp_summary, "icp_bias": icp_summary}, outdir / "baseline_summary.json")
    print(f"Wrote baselines to {outdir}")


if __name__ == "__main__":
    main()
