#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

from common import load_csv_numeric, save_yaml


def simulate_icp_bias_port_model(
    t: np.ndarray,
    v_coil: np.ndarray,
    v_bias: np.ndarray,
    params: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    gcoil0, kgcoil, lcoil0, gbias0, kgbias, cbias0, cbiasnl, vscale, kcoil, kbias, tau = params

    dt = np.diff(t)

    iL = np.zeros_like(t)
    for k in range(1, len(t)):
        di = v_coil[k - 1] / lcoil0
        iL[k] = iL[k - 1] + dt[k - 1] * di

    d = np.zeros_like(t)
    for k in range(1, len(t)):
        i_coil_eq = iL[k - 1] + (gcoil0 + kgcoil * abs(d[k - 1])) * v_coil[k - 1]
        dd = kcoil * abs(i_coil_eq) + kbias * abs(v_bias[k - 1]) / vscale - d[k - 1] / tau
        d[k] = d[k - 1] + dt[k - 1] * dd

    i_coil = iL + (gcoil0 + kgcoil * np.abs(d)) * v_coil
    q_bias = (cbias0 * (1.0 + 0.1 * np.abs(d))) * v_bias + cbiasnl * vscale * np.arctan(v_bias / vscale)
    i_bias = (gbias0 * (1.0 + kgbias * np.abs(d))) * np.tanh(v_bias / vscale) + np.gradient(q_bias, t)
    return i_coil, i_bias


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    header, data = load_csv_numeric(args.input)
    idx = {name: i for i, name in enumerate(header)}
    t = data[:, idx["time"]]
    v_coil = data[:, idx["v_coil"]]
    i_coil_meas = data[:, idx["i_coil"]]
    v_bias = data[:, idx["v_bias"]]
    i_bias_meas = data[:, idx["i_bias"]]

    x0 = np.array([1e-3, 6e-4, 2e-6, 2e-3, 0.2, 3e-11, 1e-11, 80.0, 2e-3, 5e-2, 8e-7], dtype=float)
    lb = np.array([1e-6, 1e-7, 1e-8, 1e-6, 0.0, 1e-13, 1e-13, 5.0, 1e-6, 1e-6, 1e-9], dtype=float)
    ub = np.array([1e-1, 1e-1, 1e-3, 1e-1, 3.0, 1e-8, 1e-8, 500.0, 1.0, 1.0, 1e-3], dtype=float)

    def residual(x: np.ndarray) -> np.ndarray:
        i_coil_pred, i_bias_pred = simulate_icp_bias_port_model(t, v_coil, v_bias, x)
        s1 = max(np.max(np.abs(i_coil_meas)), 1e-9)
        s2 = max(np.max(np.abs(i_bias_meas)), 1e-9)
        r1 = (i_coil_pred - i_coil_meas) / s1
        r2 = (i_bias_pred - i_bias_meas) / s2
        return np.concatenate([r1, r2])

    res = least_squares(residual, x0=x0, bounds=(lb, ub), max_nfev=500)

    names = [
        "PL_GCOIL0", "PL_KGCOIL", "PL_LCOIL0", "PL_G0", "PL_KG",
        "CBIAS0", "CBIASNL", "PL_VBSCALE", "PL_KCOIL", "PL_KBIAS", "PL_TAU"
    ]
    fitted = {k: float(v) for k, v in zip(names, res.x)}

    output = {
        "fit_success": bool(res.success),
        "cost": float(res.cost),
        "message": res.message,
        "port_level_fit": fitted,
        "ngspice_fallback_mapping": {
            "PL_GCOIL0": float(res.x[0]),
            "PL_KGCOIL": float(res.x[1]),
            "PL_LCOIL0": float(res.x[2]),
            "PL_G0": float(res.x[3]),
            "PL_KG": float(res.x[4]),
            "PL_CBP0": float(res.x[5] / 2.0),
            "PL_CBG0": float(res.x[5] / 2.0),
            "PL_CBNL": float(res.x[6]),
            "PL_VBSCALE": float(res.x[7]),
            "PL_KCOIL": float(res.x[8]),
            "PL_KBIAS": float(res.x[9]),
            "PL_TAU": float(res.x[10]),
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_yaml(output, args.output)
    print(f"Wrote fitted parameters to {args.output}")


if __name__ == "__main__":
    main()
