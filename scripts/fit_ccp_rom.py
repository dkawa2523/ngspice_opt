#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

from common import load_csv_numeric, save_yaml


def simulate_ccp_port_model(t: np.ndarray, v: np.ndarray, params: np.ndarray) -> np.ndarray:
    g0, kd, c0, cnl, vscale, alpha, tau = params
    dt = np.diff(t)
    d = np.zeros_like(t)
    for k in range(1, len(t)):
        dd = alpha * abs(v[k - 1]) / vscale - d[k - 1] / tau
        d[k] = d[k - 1] + dt[k - 1] * dd

    q = (c0 * (1.0 + 0.1 * np.abs(d))) * v + cnl * vscale * np.arctan(v / vscale)
    dqdt = np.gradient(q, t)
    i = (g0 * (1.0 + kd * np.abs(d))) * np.tanh(v / vscale) + dqdt
    return i


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    header, data = load_csv_numeric(args.input)
    idx = {name: i for i, name in enumerate(header)}
    t = data[:, idx["time"]]
    v = data[:, idx["v_port"]]
    i_meas = data[:, idx["i_port"]]

    x0 = np.array([2.0e-3, 0.20, 3.0e-11, 1.0e-11, 80.0, 8.0e-2, 4.0e-7], dtype=float)
    lb = np.array([1e-6, 0.0, 1e-13, 1e-13, 5.0, 1e-6, 1e-9], dtype=float)
    ub = np.array([1e-1, 3.0, 1e-8, 1e-8, 500.0, 5.0, 1e-3], dtype=float)

    def residual(x: np.ndarray) -> np.ndarray:
        i_pred = simulate_ccp_port_model(t, v, x)
        scale = np.maximum(np.max(np.abs(i_meas)), 1e-9)
        return (i_pred - i_meas) / scale

    res = least_squares(residual, x0=x0, bounds=(lb, ub), max_nfev=400)

    names = ["PL_G0", "PL_KD", "C_PORT0", "C_PORTNL", "PL_VSCALE", "PL_ALPHA", "PL_TAU"]
    fitted = {k: float(v) for k, v in zip(names, res.x)}
    # Map port-level fit to the fallback two-sheath parameters conservatively
    output = {
        "fit_success": bool(res.success),
        "cost": float(res.cost),
        "message": res.message,
        "port_level_fit": fitted,
        "ngspice_fallback_mapping": {
            "PL_G0": float(res.x[0]),
            "PL_KD": float(res.x[1]),
            "PL_CSP0": float(res.x[2] / 2.0),
            "PL_CSG0": float(res.x[2] / 2.0),
            "PL_CSPNL": float(res.x[3] / 2.0),
            "PL_CSGNL": float(res.x[3] / 2.0),
            "PL_VSCALE": float(res.x[4]),
            "PL_ALPHA": float(res.x[5]),
            "PL_TAU": float(res.x[6]),
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_yaml(output, args.output)
    print(f"Wrote fitted parameters to {args.output}")


if __name__ == "__main__":
    main()
