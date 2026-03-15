
#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from common import load_yaml, write_csv


def make_ccp_target(t: np.ndarray, f0: float) -> np.ndarray:
    w = 2.0 * np.pi * f0
    v = (
        165.0 * np.sin(w * t + 0.08)
        + 26.0 * np.sin(2.0 * w * t - 0.55)
        - 14.0 * np.sin(3.0 * w * t + 0.22)
    )
    return v - np.mean(v)


def make_bias_target(t: np.ndarray, f0: float) -> np.ndarray:
    w = 2.0 * np.pi * f0
    v = (
        -55.0
        + 105.0 * np.sin(w * t + 0.12)
        + 21.0 * np.sin(2.0 * w * t - 0.45)
        - 8.0 * np.sin(3.0 * w * t + 0.10)
    )
    return v


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    ccp_cfg = load_yaml(args.repo_root / "configs" / "design_space_ccp.yaml")
    icp_cfg = load_yaml(args.repo_root / "configs" / "design_space_icp_bias.yaml")

    outdir = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    t_ccp = np.arange(0.0, float(ccp_cfg["design_space"]["TSTOP"]["value"]) + 0.5 * float(ccp_cfg["design_space"]["TSTEP"]["value"]), float(ccp_cfg["design_space"]["TSTEP"]["value"]))
    v_ccp = make_ccp_target(t_ccp, float(ccp_cfg["design_space"]["F_BIAS"]["value"]))
    write_csv(outdir / "target_ccp_waveform.csv", ["time", "v_target"], zip(t_ccp, v_ccp))

    t_bias = np.arange(0.0, float(icp_cfg["design_space"]["TSTOP"]["value"]) + 0.5 * float(icp_cfg["design_space"]["TSTEP"]["value"]), float(icp_cfg["design_space"]["TSTEP"]["value"]))
    v_bias = make_bias_target(t_bias, float(icp_cfg["design_space"]["F_BIAS"]["value"]))
    write_csv(outdir / "target_bias_waveform.csv", ["time", "v_target"], zip(t_bias, v_bias))

    # Optional alternate targets for extended benchmarking.
    v_ccp_alt = (
        150.0 * np.sin(2.0 * np.pi * float(ccp_cfg["design_space"]["F_BIAS"]["value"]) * t_ccp - 0.05)
        + 34.0 * np.sin(2.0 * 2.0 * np.pi * float(ccp_cfg["design_space"]["F_BIAS"]["value"]) * t_ccp + 0.75)
        + 10.0 * np.sin(3.0 * 2.0 * np.pi * float(ccp_cfg["design_space"]["F_BIAS"]["value"]) * t_ccp - 0.10)
    )
    v_ccp_alt = v_ccp_alt - np.mean(v_ccp_alt)
    write_csv(outdir / "target_ccp_waveform_alt.csv", ["time", "v_target"], zip(t_ccp, v_ccp_alt))

    v_bias_alt = (
        -35.0
        + 92.0 * np.sin(2.0 * np.pi * float(icp_cfg["design_space"]["F_BIAS"]["value"]) * t_bias + 0.25)
        + 30.0 * np.sin(2.0 * 2.0 * np.pi * float(icp_cfg["design_space"]["F_BIAS"]["value"]) * t_bias - 0.60)
    )
    write_csv(outdir / "target_bias_waveform_alt.csv", ["time", "v_target"], zip(t_bias, v_bias_alt))

    print(f"Wrote targets to {outdir}")


if __name__ == "__main__":
    main()
