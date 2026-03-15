
#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import yaml


@dataclass
class TrialResult:
    design: Dict[str, Any]
    aggregate_objective: float
    mean_metrics: Dict[str, float]
    std_metrics: Dict[str, float]
    deck_paths: List[str]
    waveform_paths: List[str]


def load_yaml(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data


def save_yaml(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def save_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_csv_numeric(path: Path) -> tuple[list[str], np.ndarray]:
    with Path(path).open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
    data = np.loadtxt(path, delimiter=",", skiprows=1)
    if data.ndim == 1:
        data = data[None, :]
    return header, data


def write_csv(path: Path, header: Iterable[str], rows: Iterable[Iterable[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(list(header))
        for row in rows:
            writer.writerow(list(row))


def load_target_waveform(path: Path) -> tuple[np.ndarray, np.ndarray]:
    header, data = load_csv_numeric(path)
    idx = {name: i for i, name in enumerate(header)}
    return data[:, idx["time"]], data[:, idx["v_target"]]


def interp_to(t_new: np.ndarray, t_old: np.ndarray, y_old: np.ndarray) -> np.ndarray:
    return np.interp(t_new, t_old, y_old)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.asarray(x, dtype=float) ** 2)))


def harmonic_amplitude(t: np.ndarray, y: np.ndarray, f0: float, n: int = 1) -> float:
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    w = 2.0 * np.pi * f0 * n
    s = np.sin(w * t)
    c = np.cos(w * t)
    a = 2.0 * np.mean(y * s)
    b = 2.0 * np.mean(y * c)
    return float(np.sqrt(a * a + b * b))


def summarize_metric_dicts(metrics: List[Dict[str, float]]) -> tuple[Dict[str, float], Dict[str, float]]:
    keys = list(metrics[0].keys())
    mean = {}
    std = {}
    for k in keys:
        arr = np.array([m[k] for m in metrics], dtype=float)
        mean[k] = float(np.mean(arr))
        std[k] = float(np.std(arr, ddof=0))
    return mean, std


def _penalize_peak_current(i_peak: float, max_peak_current: float) -> float:
    r = i_peak / max(max_peak_current, 1e-12)
    if r <= 1.0:
        return 0.05 * r
    return 0.05 + (r - 1.0) ** 2


def evaluate_ccp_objective(sim_data: np.ndarray, target_time: np.ndarray, target_v: np.ndarray, objective_cfg: dict) -> Dict[str, float]:
    t = sim_data[:, 0]
    v = sim_data[:, 1]
    i = sim_data[:, 2]
    target_v_interp = interp_to(t, target_time, target_v)
    v_rmse = rms(v - target_v_interp)
    i_peak = float(np.max(np.abs(i)))
    avg_power = float(np.mean(v * i))
    selfbias = float(np.mean(v))
    objective = (
        float(objective_cfg["w_v_rmse"]) * v_rmse
        + float(objective_cfg["w_i_peak"]) * _penalize_peak_current(i_peak, float(objective_cfg["max_peak_current_A"]))
        + float(objective_cfg["w_avg_power"]) * abs(avg_power) / 100.0
        + float(objective_cfg["w_selfbias"]) * abs(selfbias - float(objective_cfg["target_selfbias"])) / 100.0
    )
    return {
        "objective": float(objective),
        "v_rmse": float(v_rmse),
        "i_peak": float(i_peak),
        "avg_power": float(avg_power),
        "selfbias": float(selfbias),
    }


def evaluate_icp_bias_objective(sim_data: np.ndarray, target_time: np.ndarray, target_v: np.ndarray, objective_cfg: dict) -> Dict[str, float]:
    t = sim_data[:, 0]
    v_coil = sim_data[:, 1]
    i_coil = sim_data[:, 2]
    v_bias = sim_data[:, 3]
    i_bias = sim_data[:, 4]
    target_v_interp = interp_to(t, target_time, target_v)
    v_rmse = rms(v_bias - target_v_interp)
    i_peak = float(max(np.max(np.abs(i_coil)), np.max(np.abs(i_bias))))
    avg_power = float(np.mean(v_coil * i_coil + v_bias * i_bias))
    selfbias = float(np.mean(v_bias))
    objective = (
        float(objective_cfg["w_v_rmse"]) * v_rmse
        + float(objective_cfg["w_i_peak"]) * _penalize_peak_current(i_peak, float(objective_cfg["max_peak_current_A"]))
        + float(objective_cfg["w_avg_power"]) * abs(avg_power) / 100.0
        + float(objective_cfg["w_selfbias"]) * abs(selfbias - float(objective_cfg["target_selfbias"])) / 100.0
    )
    return {
        "objective": float(objective),
        "v_rmse": float(v_rmse),
        "i_peak": float(i_peak),
        "avg_power": float(avg_power),
        "selfbias": float(selfbias),
    }


def sample_one(spec: dict, rng) -> Any:
    typ = spec["type"]
    if typ == "fixed":
        return spec["value"]
    if typ == "choice":
        return rng.choice(list(spec["values"]))
    if typ == "range":
        low = float(spec["low"])
        high = float(spec["high"])
        if spec.get("log", False):
            return float(math.exp(rng.uniform(math.log(low), math.log(high))))
        return float(rng.uniform(low, high))
    raise ValueError(f"Unknown spec type: {typ}")


def sample_space(space: dict, rng) -> Dict[str, Any]:
    return {k: sample_one(v, rng) for k, v in space.items()}


def perturb_around(design: Dict[str, Any], space: dict, rng, sigma_fraction: float) -> Dict[str, Any]:
    out = {}
    for k, spec in space.items():
        typ = spec["type"]
        if typ in ("fixed", "choice"):
            out[k] = design[k] if typ == "fixed" or rng.random() > 0.15 else rng.choice(list(spec["values"]))
        elif typ == "range":
            low = float(spec["low"])
            high = float(spec["high"])
            val = float(design[k])
            span = high - low
            if spec.get("log", False):
                lv = math.log(val)
                l_low = math.log(low)
                l_high = math.log(high)
                lv += rng.gauss(0.0, sigma_fraction * (l_high - l_low))
                lv = min(max(lv, l_low), l_high)
                out[k] = float(math.exp(lv))
            else:
                val += rng.gauss(0.0, sigma_fraction * span)
                val = min(max(val, low), high)
                out[k] = float(val)
        else:
            raise ValueError(f"Unknown spec type: {typ}")
    return out


def derive_lumped_parasitics(cfg: dict, prefix: str = "CABLE") -> Dict[str, float]:
    length = float(cfg[f"{prefix}_LEN_M"])
    return {
        f"R_{prefix}": float(cfg[f"{prefix}_R_PER_M"]) * length,
        f"L_{prefix}": float(cfg[f"{prefix}_L_PER_M"]) * length,
        f"C_{prefix}": float(cfg[f"{prefix}_C_PER_M"]) * length,
    }


def make_match_block_ccp(topology: str) -> str:
    if topology == "PI":
        return "\n".join([
            "C_MATCH_IN SRC_INT N_PI_MID {C_MATCH_IN}",
            "L_MATCH N_PI_MID N_MATCH {L_MATCH}",
            "C_MATCH_OUT N_MATCH 0 {C_MATCH_OUT}",
        ])
    return "\n".join([
        "L_MATCH SRC_INT N_MATCH {L_MATCH}",
        "C_MATCH_OUT N_MATCH 0 {C_MATCH_OUT}",
    ])


def make_match_block_icp(topology: str, kind: str) -> str:
    if kind not in {"coil", "bias"}:
        raise ValueError(kind)
    if kind == "coil":
        l_name = "L_COIL_MATCH"
        cin = "C_COIL_MATCH_IN"
        cout = "C_COIL_MATCH_OUT"
        src = "ICP_INT"
        out = "N_COIL_MATCH"
    else:
        l_name = "L_BIAS_MATCH"
        cin = "C_BIAS_MATCH_IN"
        cout = "C_BIAS_MATCH_OUT"
        src = "BIAS_INT"
        out = "N_BIAS_MATCH"
    if topology == "PI":
        return "\n".join([
            f"{cin} {src} N_{kind.upper()}_PI_MID {{{cin}}}",
            f"{l_name} N_{kind.upper()}_PI_MID {out} {{{l_name}}}",
            f"{cout} {out} 0 {{{cout}}}",
        ])
    return "\n".join([
        f"{l_name} {src} {out} {{{l_name}}}",
        f"{cout} {out} 0 {{{cout}}}",
    ])


def replace_tokens(template_text: str, mapping: Dict[str, Any]) -> str:
    out = template_text
    for k, v in mapping.items():
        out = out.replace(f"@@{k}@@", str(v))
    return out


def run_ngspice(deck_path: Path, log_path: Path, ngspice_bin: str = "ngspice") -> None:
    with log_path.open("w", encoding="utf-8") as logf:
        proc = subprocess.run([ngspice_bin, "-b", str(deck_path)], stdout=logf, stderr=subprocess.STDOUT, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ngspice failed: {deck_path}")


def read_wrdata_real(path: Path) -> tuple[list[str], np.ndarray]:
    header = None
    rows = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if header is None:
                header = line.split()
                continue
            rows.append([float(x) for x in line.split()])
    if header is None:
        raise ValueError(f"Empty wrdata file: {path}")
    arr = np.array(rows, dtype=float)
    return header, arr
