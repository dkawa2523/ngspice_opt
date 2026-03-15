
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import math
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

from common import (
    evaluate_ccp_objective,
    evaluate_icp_bias_objective,
    harmonic_amplitude,
    load_csv_numeric,
    load_target_waveform,
    load_yaml,
    rms,
    sample_space,
    save_json,
    save_yaml,
    write_csv,
)
from fit_ccp_rom import simulate_ccp_port_model
from fit_icp_bias_rom import simulate_icp_bias_port_model
from generate_targets import make_bias_target, make_ccp_target


@dataclass
class CCPCondition:
    family: str
    pressure_proxy: float
    wall_condition: float
    asymmetry: float
    resonance_shift: float
    nonlinearity_boost: float
    memory_boost: float
    preferred_topology: str
    noise_level_v: float
    noise_level_i: float


@dataclass
class ICPCondition:
    family: str
    pressure_proxy: float
    wall_condition: float
    density_bias: float
    coil_coupling_shift: float
    bias_nonlinearity_boost: float
    memory_boost: float
    preferred_coil_topology: str
    preferred_bias_topology: str
    noise_level_v: float
    noise_level_i: float


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _split_counts(total: int, ratios: Tuple[float, float, float, float]) -> Dict[str, int]:
    names = ["train", "val", "test_id", "test_ood"]
    raw = np.array(ratios, dtype=float) * total
    counts = np.floor(raw).astype(int)
    while counts.sum() < total:
        idx = int(np.argmax(raw - counts))
        counts[idx] += 1
    return {k: int(v) for k, v in zip(names, counts)}


def _make_ccp_condition(seed: int, family: str) -> CCPCondition:
    rng = _rng(seed)
    if family == "nominal":
        return CCPCondition(
            family=family,
            pressure_proxy=float(rng.uniform(0.8, 1.2)),
            wall_condition=float(rng.uniform(0.9, 1.1)),
            asymmetry=float(rng.uniform(0.05, 0.45)),
            resonance_shift=float(rng.uniform(-0.18, 0.18)),
            nonlinearity_boost=float(rng.uniform(0.9, 1.2)),
            memory_boost=float(rng.uniform(0.9, 1.15)),
            preferred_topology=str(rng.choice(["L", "PI"])),
            noise_level_v=float(rng.uniform(0.002, 0.008)),
            noise_level_i=float(rng.uniform(0.004, 0.012)),
        )
    if family == "shifted_surface":
        return CCPCondition(
            family=family,
            pressure_proxy=float(rng.uniform(0.7, 1.25)),
            wall_condition=float(rng.uniform(1.05, 1.35)),
            asymmetry=float(rng.uniform(0.2, 0.65)),
            resonance_shift=float(rng.uniform(-0.25, 0.25)),
            nonlinearity_boost=float(rng.uniform(1.05, 1.35)),
            memory_boost=float(rng.uniform(1.05, 1.30)),
            preferred_topology=str(rng.choice(["L", "PI"])),
            noise_level_v=float(rng.uniform(0.003, 0.010)),
            noise_level_i=float(rng.uniform(0.006, 0.016)),
        )
    if family == "ood_nonlin":
        return CCPCondition(
            family=family,
            pressure_proxy=float(rng.uniform(0.55, 1.40)),
            wall_condition=float(rng.uniform(0.8, 1.4)),
            asymmetry=float(rng.uniform(0.45, 0.95)),
            resonance_shift=float(rng.uniform(-0.35, 0.35)),
            nonlinearity_boost=float(rng.uniform(1.25, 1.70)),
            memory_boost=float(rng.uniform(1.20, 1.60)),
            preferred_topology=str(rng.choice(["L", "PI"])),
            noise_level_v=float(rng.uniform(0.006, 0.015)),
            noise_level_i=float(rng.uniform(0.010, 0.024)),
        )
    raise ValueError(family)


def _make_icp_condition(seed: int, family: str) -> ICPCondition:
    rng = _rng(seed)
    if family == "nominal":
        return ICPCondition(
            family=family,
            pressure_proxy=float(rng.uniform(0.8, 1.2)),
            wall_condition=float(rng.uniform(0.9, 1.1)),
            density_bias=float(rng.uniform(0.9, 1.1)),
            coil_coupling_shift=float(rng.uniform(-0.18, 0.18)),
            bias_nonlinearity_boost=float(rng.uniform(0.9, 1.2)),
            memory_boost=float(rng.uniform(0.9, 1.15)),
            preferred_coil_topology=str(rng.choice(["L", "PI"])),
            preferred_bias_topology=str(rng.choice(["L", "PI"])),
            noise_level_v=float(rng.uniform(0.002, 0.008)),
            noise_level_i=float(rng.uniform(0.004, 0.012)),
        )
    if family == "shifted_surface":
        return ICPCondition(
            family=family,
            pressure_proxy=float(rng.uniform(0.75, 1.30)),
            wall_condition=float(rng.uniform(1.0, 1.35)),
            density_bias=float(rng.uniform(0.95, 1.2)),
            coil_coupling_shift=float(rng.uniform(-0.24, 0.24)),
            bias_nonlinearity_boost=float(rng.uniform(1.05, 1.35)),
            memory_boost=float(rng.uniform(1.05, 1.30)),
            preferred_coil_topology=str(rng.choice(["L", "PI"])),
            preferred_bias_topology=str(rng.choice(["L", "PI"])),
            noise_level_v=float(rng.uniform(0.003, 0.010)),
            noise_level_i=float(rng.uniform(0.006, 0.016)),
        )
    if family == "ood_nonlin":
        return ICPCondition(
            family=family,
            pressure_proxy=float(rng.uniform(0.6, 1.45)),
            wall_condition=float(rng.uniform(0.85, 1.45)),
            density_bias=float(rng.uniform(0.8, 1.35)),
            coil_coupling_shift=float(rng.uniform(-0.32, 0.32)),
            bias_nonlinearity_boost=float(rng.uniform(1.25, 1.70)),
            memory_boost=float(rng.uniform(1.20, 1.55)),
            preferred_coil_topology=str(rng.choice(["L", "PI"])),
            preferred_bias_topology=str(rng.choice(["L", "PI"])),
            noise_level_v=float(rng.uniform(0.006, 0.015)),
            noise_level_i=float(rng.uniform(0.010, 0.025)),
        )
    raise ValueError(family)


def _ccp_truth_params_from_condition(cond: CCPCondition, rng: np.random.Generator) -> Dict[str, float]:
    return {
        "g0": float(np.exp(rng.uniform(np.log(1.2e-3), np.log(4.8e-3))) * cond.pressure_proxy ** 0.12),
        "kd": float(rng.uniform(0.08, 0.55) * cond.nonlinearity_boost),
        "c0": float(np.exp(rng.uniform(np.log(1.2e-11), np.log(6.5e-11))) * cond.wall_condition),
        "cnl": float(np.exp(rng.uniform(np.log(8.0e-13), np.log(1.8e-11))) * cond.nonlinearity_boost),
        "vscale": float(rng.uniform(35.0, 140.0) / cond.pressure_proxy ** 0.08),
        "alpha": float(np.exp(rng.uniform(np.log(2.5e-3), np.log(0.18))) * cond.nonlinearity_boost),
        "tau": float(np.exp(rng.uniform(np.log(7.0e-8), np.log(2.0e-6))) * cond.memory_boost),
        "beta_mem": float(rng.uniform(0.01, 0.08) * cond.memory_boost),
        "c_asym": float(rng.uniform(0.03, 0.18) * cond.asymmetry),
        "g_emiss": float(rng.uniform(0.0, 2.5e-3) * cond.wall_condition),
        "c_stray": float(rng.uniform(0.4e-12, 6.0e-12)),
        "tau_s": float(np.exp(rng.uniform(np.log(8.0e-8), np.log(3.0e-6))) * cond.memory_boost),
    }


def _icp_truth_params_from_condition(cond: ICPCondition, rng: np.random.Generator) -> Dict[str, float]:
    return {
        "gcoil0": float(np.exp(rng.uniform(np.log(2.0e-4), np.log(3.5e-3))) * cond.density_bias),
        "kgcoil": float(np.exp(rng.uniform(np.log(1.0e-4), np.log(3.0e-3))) * (1.0 + 0.3 * cond.density_bias)),
        "lcoil0": float(np.exp(rng.uniform(np.log(4.0e-7), np.log(5.0e-6))) * (1.0 + 0.1 * cond.coil_coupling_shift)),
        "gbias0": float(np.exp(rng.uniform(np.log(7.0e-4), np.log(4.5e-3))) * cond.pressure_proxy ** 0.1),
        "kgbias": float(rng.uniform(0.08, 0.55) * cond.bias_nonlinearity_boost),
        "cbias0": float(np.exp(rng.uniform(np.log(1.0e-11), np.log(6.0e-11))) * cond.wall_condition),
        "cbiasnl": float(np.exp(rng.uniform(np.log(8.0e-13), np.log(2.0e-11))) * cond.bias_nonlinearity_boost),
        "vscale": float(rng.uniform(30.0, 120.0) / cond.pressure_proxy ** 0.08),
        "kcoil": float(np.exp(rng.uniform(np.log(6.0e-4), np.log(8.0e-3))) * cond.density_bias),
        "kbias": float(np.exp(rng.uniform(np.log(3.0e-3), np.log(1.8e-1))) * cond.bias_nonlinearity_boost),
        "tau": float(np.exp(rng.uniform(np.log(7.0e-8), np.log(2.0e-6))) * cond.memory_boost),
        "tau_h": float(np.exp(rng.uniform(np.log(4.0e-8), np.log(8.0e-7))) * cond.memory_boost),
        "cx": float(rng.uniform(0.4e-12, 6.0e-12)),
        "gcoil_mem": float(rng.uniform(0.0, 8.0e-4)),
        "bias_asym": float(rng.uniform(0.03, 0.18) * cond.bias_nonlinearity_boost),
    }


def _resonance_score(detune: float, sigma: float = 0.22) -> float:
    return float(np.exp(-0.5 * (detune / sigma) ** 2))


def _safe_log_ratio(a: float, b: float) -> float:
    return float(np.log(max(a, 1e-30) / max(b, 1e-30)))


def _make_ccp_port_voltage(
    t: np.ndarray,
    design: Dict[str, Any],
    target_v: np.ndarray,
    cond: CCPCondition,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, float]]:
    f = float(design["F_BIAS"])
    w = 2.0 * np.pi * f
    vac = float(design["VAC_BIAS"])
    topology = str(design["topology"])
    c_cable = float(design["CABLE_C_PER_M"]) * float(design["CABLE_LEN_M"])
    ceq = float(design["C_MATCH_OUT"]) + 0.35 * float(design["C_MATCH_IN"]) + 0.25 * c_cable
    f0 = 1.0 / (2.0 * np.pi * math.sqrt(max(float(design["L_MATCH"]) * max(ceq, 1e-15), 1e-30)))
    f_ideal = f * (1.0 + cond.resonance_shift)
    detune = _safe_log_ratio(f0, f_ideal)

    topology_bonus = 1.02 if topology == cond.preferred_topology else 0.92
    block_factor = float(np.exp(-abs(_safe_log_ratio(float(design["C_BLOCK"]), 3.0e-9)) / 2.5))
    cable_penalty = float(np.exp(-0.10 * float(design["CABLE_LEN_M"])))
    return_penalty = float(np.exp(-0.08 * float(design["RETURN_LEN_M"])))
    q_match = float(np.clip(0.18 + 0.74 * _resonance_score(detune) * topology_bonus * block_factor * cable_penalty * return_penalty, 0.05, 0.98))

    phase = 0.65 * detune + 0.09 * (float(design["CABLE_LEN_M"]) - float(design["RETURN_LEN_M"])) + (0.04 if topology == "PI" else -0.02)
    src = vac * np.sin(w * t)
    target_scaled = target_v / max(rms(target_v), 1e-12) * (0.78 * vac)
    vdc = -(12.0 + 0.12 * vac) * cond.asymmetry * (0.20 + 0.80 * (1.0 - q_match))

    h2 = (0.03 + 0.18 * (1.0 - q_match) + 0.03 * cond.nonlinearity_boost)
    h3 = (0.02 + 0.10 * abs(detune) + 0.02 * cond.memory_boost)
    ripple = 0.02 * vac * np.sin(0.5 * w * t + 0.5 * phase)

    port = (
        vdc
        + q_match * np.roll(target_scaled, int(round(phase / (w * (t[1] - t[0])))))
        + (1.0 - q_match) * vac * np.sin(w * t + phase)
        + vac * h2 * np.sin(2.0 * w * t - 0.45 + 1.3 * phase)
        + vac * h3 * np.sin(3.0 * w * t + 0.10 - 0.7 * phase)
        + ripple
    )

    meta = {
        "f0": float(f0),
        "f_ideal": float(f_ideal),
        "detune": float(detune),
        "q_match": float(q_match),
        "phase": float(phase),
        "vdc": float(vdc),
    }
    return src, port, meta


def _make_icp_bias_port_voltages(
    t: np.ndarray,
    design: Dict[str, Any],
    target_bias: np.ndarray,
    cond: ICPCondition,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, float]]:
    f_coil = float(design["F_ICP"])
    f_bias = float(design["F_BIAS"])
    wc = 2.0 * np.pi * f_coil
    wb = 2.0 * np.pi * f_bias

    v_icp = float(design["VICP_AC"])
    v_bias_ac = float(design["VBIAS_AC"])
    v_bias_dc = float(design["VBIAS_DC"])

    coil_top = str(design["coil_topology"])
    bias_top = str(design["bias_topology"])

    c_coil = float(design["C_COIL_MATCH_OUT"]) + 0.3 * float(design["C_COIL_MATCH_IN"]) + 0.25 * float(design["FEED_C_PER_M"]) * float(design["COIL_FEED_LEN_M"])
    f0_coil = 1.0 / (2.0 * np.pi * math.sqrt(max(float(design["L_COIL_MATCH"]) * max(c_coil, 1e-15), 1e-30)))
    f_ideal_coil = f_coil * (1.0 + cond.coil_coupling_shift)
    detune_coil = _safe_log_ratio(f0_coil, f_ideal_coil)
    q_coil = float(np.clip(
        0.20
        + 0.72
        * _resonance_score(detune_coil, 0.26)
        * (1.02 if coil_top == cond.preferred_coil_topology else 0.93)
        * np.exp(-0.10 * float(design["COIL_FEED_LEN_M"])),
        0.05,
        0.98,
    ))

    c_bias = float(design["C_BIAS_MATCH_OUT"]) + 0.3 * float(design["C_BIAS_MATCH_IN"]) + 0.25 * float(design["FEED_C_PER_M"]) * float(design["BIAS_FEED_LEN_M"])
    f0_bias = 1.0 / (2.0 * np.pi * math.sqrt(max(float(design["L_BIAS_MATCH"]) * max(c_bias, 1e-15), 1e-30)))
    f_ideal_bias = f_bias * (1.0 + 0.6 * cond.coil_coupling_shift)
    detune_bias = _safe_log_ratio(f0_bias, f_ideal_bias)
    q_bias = float(np.clip(
        0.18
        + 0.74
        * _resonance_score(detune_bias, 0.28)
        * (1.02 if bias_top == cond.preferred_bias_topology else 0.92)
        * np.exp(-0.09 * float(design["BIAS_FEED_LEN_M"]))
        * np.exp(-abs(_safe_log_ratio(float(design["C_BLOCK_BIAS"]), 4.0e-9)) / 2.8),
        0.04,
        0.98,
    ))

    phase_coil = 0.55 * detune_coil + 0.05 * float(design["COIL_FEED_LEN_M"])
    phase_bias = 0.70 * detune_bias + 0.05 * float(design["BIAS_FEED_LEN_M"]) - 0.08 * cond.density_bias

    src_coil = v_icp * np.sin(wc * t)
    coil_h2 = 0.015 + 0.08 * (1.0 - q_coil)
    v_coil = (
        (0.55 + 0.45 * q_coil) * v_icp * np.sin(wc * t + phase_coil)
        + v_icp * coil_h2 * np.sin(2.0 * wc * t - 0.35)
    )

    target_scaled = target_bias / max(rms(target_bias), 1e-12) * (0.78 * max(v_bias_ac, 20.0))
    effective_dc = v_bias_dc - 16.0 * cond.density_bias * (0.20 + 0.80 * (1.0 - q_bias))
    bias_h2 = 0.03 + 0.16 * (1.0 - q_bias) + 0.03 * cond.bias_nonlinearity_boost
    bias_h3 = 0.015 + 0.08 * abs(detune_bias)
    v_bias = (
        effective_dc
        + q_bias * np.roll(target_scaled, int(round(phase_bias / (wb * (t[1] - t[0])))))
        + (1.0 - q_bias) * v_bias_ac * np.sin(wb * t + phase_bias)
        + v_bias_ac * bias_h2 * np.sin(2.0 * wb * t - 0.42 + 0.7 * phase_bias)
        + v_bias_ac * bias_h3 * np.sin(3.0 * wb * t + 0.15)
    )

    meta = {
        "f0_coil": float(f0_coil),
        "f0_bias": float(f0_bias),
        "detune_coil": float(detune_coil),
        "detune_bias": float(detune_bias),
        "q_coil": float(q_coil),
        "q_bias": float(q_bias),
        "phase_coil": float(phase_coil),
        "phase_bias": float(phase_bias),
        "effective_dc": float(effective_dc),
    }
    return src_coil, v_coil, v_bias, meta


def _hidden_ccp_current(
    t: np.ndarray,
    v_port: np.ndarray,
    v_src: np.ndarray,
    truth: Dict[str, float],
    cond: CCPCondition,
) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    base = simulate_ccp_port_model(
        t,
        v_port,
        np.array([truth["g0"], truth["kd"], truth["c0"], truth["cnl"], truth["vscale"], truth["alpha"], truth["tau"]], dtype=float),
    )
    dt = t[1] - t[0]
    d = np.zeros_like(t)
    s = np.zeros_like(t)
    dvdt = np.gradient(v_port, t)
    dvsrcdt = np.gradient(v_src, t)
    for k in range(1, len(t)):
        dd = truth["beta_mem"] * abs(dvdt[k - 1]) / max(np.max(np.abs(dvdt)), 1e-9) + truth["alpha"] * abs(v_port[k - 1]) / max(truth["vscale"], 1e-9) - d[k - 1] / truth["tau"]
        ds = 0.9 * cond.asymmetry * np.tanh(v_port[k - 1] / max(1.4 * truth["vscale"], 1e-9)) - s[k - 1] / truth["tau_s"]
        d[k] = d[k - 1] + dt * dd
        s[k] = s[k - 1] + dt * ds
    q_extra = truth["c_asym"] * truth["c0"] * v_port * s + 0.08 * truth["c0"] * truth["vscale"] * np.tanh(v_port / max(truth["vscale"], 1e-9))
    i_extra = np.gradient(q_extra, t) + truth["g_emiss"] * np.maximum(v_port, 0.0) ** 2 / (truth["vscale"] ** 2 + np.maximum(v_port, 0.0) ** 2 + 1e-12) + truth["c_stray"] * dvsrcdt
    i = base + i_extra
    return i, {"density_state": d, "asym_state": s, "q_extra": q_extra}


def _hidden_icp_bias_currents(
    t: np.ndarray,
    v_coil: np.ndarray,
    v_bias: np.ndarray,
    truth: Dict[str, float],
    cond: ICPCondition,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, np.ndarray]]:
    i_coil_base, i_bias_base = simulate_icp_bias_port_model(
        t,
        v_coil,
        v_bias,
        np.array([
            truth["gcoil0"], truth["kgcoil"], truth["lcoil0"], truth["gbias0"], truth["kgbias"],
            truth["cbias0"], truth["cbiasnl"], truth["vscale"], truth["kcoil"], truth["kbias"], truth["tau"]
        ], dtype=float),
    )
    dt = t[1] - t[0]
    d = np.zeros_like(t)
    h = np.zeros_like(t)
    for k in range(1, len(t)):
        dd = truth["kcoil"] * abs(i_coil_base[k - 1]) + truth["kbias"] * abs(v_bias[k - 1]) / max(truth["vscale"], 1e-9) - d[k - 1] / truth["tau"]
        dh = 0.18 * (i_coil_base[k - 1] ** 2) / max(np.max(i_coil_base ** 2), 1e-9) + 0.05 * abs(v_bias[k - 1]) / max(np.max(np.abs(v_bias)), 1e-9) - h[k - 1] / truth["tau_h"]
        d[k] = d[k - 1] + dt * dd
        h[k] = h[k - 1] + dt * dh
    di_coil_dt = np.gradient(i_coil_base, t)
    q_extra = truth["bias_asym"] * truth["cbias0"] * v_bias * np.tanh(v_bias / max(truth["vscale"], 1e-9)) + 0.05 * truth["cbias0"] * truth["vscale"] * h
    i_coil = i_coil_base + truth["gcoil_mem"] * h * v_coil
    i_bias = i_bias_base + np.gradient(q_extra, t) + truth["cx"] * di_coil_dt
    return i_coil, i_bias, {"density_state": d, "heating_state": h, "q_extra": q_extra}


def _add_measurement_noise(y: np.ndarray, scale_fraction: float, rng: np.random.Generator) -> np.ndarray:
    scale = max(np.max(np.abs(y)), 1e-12)
    return y + rng.normal(0.0, scale_fraction * scale, size=y.shape)


def _basic_split_labels(n: int, counts: Dict[str, int]) -> List[str]:
    labels = []
    for name in ["train", "val", "test_id", "test_ood"]:
        labels.extend([name] * counts[name])
    assert len(labels) == n
    return labels


def _rolling_shift(signal: np.ndarray, shift: int) -> np.ndarray:
    if shift == 0:
        return signal.copy()
    return np.roll(signal, int(shift))


def _ccp_case_metrics(t: np.ndarray, v_port: np.ndarray, i_port: np.ndarray, target_t: np.ndarray, target_v: np.ndarray, design: Dict[str, Any], cond: CCPCondition, states: Dict[str, np.ndarray], objective_cfg: dict) -> Dict[str, float]:
    sim_data = np.column_stack([t, v_port, i_port, np.zeros_like(t)])
    metrics = evaluate_ccp_objective(sim_data, target_t, target_v, objective_cfg)
    f0 = float(design["F_BIAS"])
    p_abs = float(np.mean(v_port * i_port))
    metrics.update({
        "v_rms": float(rms(v_port)),
        "i_rms": float(rms(i_port)),
        "p_abs": p_abs,
        "v_h1": harmonic_amplitude(t, v_port, f0, 1),
        "v_h2": harmonic_amplitude(t, v_port, f0, 2),
        "v_h3": harmonic_amplitude(t, v_port, f0, 3),
        "i_h1": harmonic_amplitude(t, i_port, f0, 1),
        "i_h2": harmonic_amplitude(t, i_port, f0, 2),
        "i_h3": harmonic_amplitude(t, i_port, f0, 3),
        "density_proxy": float(np.mean(states["density_state"])),
        "ion_flux_proxy": float(np.mean(states["density_state"]) * (1.0 + 0.08 * np.sqrt(abs(p_abs) + 1e-9))),
        "ion_energy_proxy": float(abs(np.mean(v_port)) + 0.18 * harmonic_amplitude(t, v_port, f0, 2)),
        "pressure_proxy": float(cond.pressure_proxy),
        "wall_condition": float(cond.wall_condition),
        "asymmetry": float(cond.asymmetry),
    })
    return metrics


def _icp_case_metrics(t: np.ndarray, v_coil: np.ndarray, i_coil: np.ndarray, v_bias: np.ndarray, i_bias: np.ndarray, target_t: np.ndarray, target_v: np.ndarray, design: Dict[str, Any], cond: ICPCondition, states: Dict[str, np.ndarray], objective_cfg: dict) -> Dict[str, float]:
    sim_data = np.column_stack([t, v_coil, i_coil, v_bias, i_bias])
    metrics = evaluate_icp_bias_objective(sim_data, target_t, target_v, objective_cfg)
    f_coil = float(design["F_ICP"])
    f_bias = float(design["F_BIAS"])
    p_coil = float(np.mean(v_coil * i_coil))
    p_bias = float(np.mean(v_bias * i_bias))
    metrics.update({
        "v_bias_rms": float(rms(v_bias)),
        "i_bias_rms": float(rms(i_bias)),
        "v_coil_rms": float(rms(v_coil)),
        "i_coil_rms": float(rms(i_coil)),
        "p_abs_coil": p_coil,
        "p_abs_bias": p_bias,
        "v_bias_h1": harmonic_amplitude(t, v_bias, f_bias, 1),
        "v_bias_h2": harmonic_amplitude(t, v_bias, f_bias, 2),
        "v_bias_h3": harmonic_amplitude(t, v_bias, f_bias, 3),
        "i_bias_h1": harmonic_amplitude(t, i_bias, f_bias, 1),
        "i_bias_h2": harmonic_amplitude(t, i_bias, f_bias, 2),
        "i_bias_h3": harmonic_amplitude(t, i_bias, f_bias, 3),
        "v_coil_h1": harmonic_amplitude(t, v_coil, f_coil, 1),
        "i_coil_h1": harmonic_amplitude(t, i_coil, f_coil, 1),
        "density_proxy": float(np.mean(states["density_state"])),
        "ion_flux_proxy": float(np.mean(states["density_state"]) * (1.0 + 0.04 * np.sqrt(abs(p_bias) + abs(p_coil) + 1e-9))),
        "ion_energy_proxy": float(abs(np.mean(v_bias)) + 0.20 * harmonic_amplitude(t, v_bias, f_bias, 2)),
        "pressure_proxy": float(cond.pressure_proxy),
        "wall_condition": float(cond.wall_condition),
        "density_bias": float(cond.density_bias),
    })
    return metrics


def _ensure_clean_dir(path: Path) -> None:
    if path.exists():
        def _onerror(_func, _path, exc_info):
            # AppleDouble sidecar files (._*) on external volumes can disappear
            # during traversal; ignore only missing-path errors.
            if isinstance(exc_info[1], FileNotFoundError):
                return
            raise exc_info[1]

        shutil.rmtree(path, onerror=_onerror)
    path.mkdir(parents=True, exist_ok=True)


def generate_identification_ccp(repo_root: Path, out_root: Path, n_total: int = 96, seed: int = 20260315) -> Dict[str, Any]:
    rng = _rng(seed)
    cfg = load_yaml(repo_root / "configs" / "design_space_ccp.yaml")
    target_t, target_v = load_target_waveform(repo_root / cfg["target_waveform"])
    design_space = cfg["design_space"]
    counts = _split_counts(n_total, (0.625, 0.125, 0.125, 0.125))
    split_labels = _basic_split_labels(n_total, counts)

    base_dir = out_root / "ccp_identification"
    _ensure_clean_dir(base_dir)
    for s in counts.keys():
        (base_dir / s).mkdir(parents=True, exist_ok=True)

    index_rows = []
    for i in range(n_total):
        split = split_labels[i]
        family = "nominal" if split != "test_ood" else "ood_nonlin"
        cond = _make_ccp_condition(seed + 1000 + i, family)
        design = sample_space(design_space, rng)
        if split == "test_ood":
            design["CABLE_LEN_M"] = float(min(4.0, max(0.2, design["CABLE_LEN_M"] * 1.18)))
            design["RETURN_LEN_M"] = float(min(2.0, max(0.05, design["RETURN_LEN_M"] * 1.18)))
        t = target_t.copy()
        v_src, v_port_clean, design_meta = _make_ccp_port_voltage(t, design, target_v, cond)
        truth = _ccp_truth_params_from_condition(cond, rng)
        i_clean, states = _hidden_ccp_current(t, v_port_clean, v_src, truth, cond)
        v_meas = _add_measurement_noise(v_port_clean, cond.noise_level_v, rng)
        i_meas = _add_measurement_noise(i_clean, cond.noise_level_i, rng)

        case_id = f"ccp_id_{i:04d}"
        file_path = base_dir / split / f"{case_id}.csv"
        rows = zip(t, v_meas, i_meas, v_port_clean, i_clean, v_src, states["density_state"], states["asym_state"])
        write_csv(file_path, ["time", "v_port", "i_port", "v_port_clean", "i_port_clean", "v_src", "density_state", "asym_state"], rows)

        metrics = _ccp_case_metrics(t, v_port_clean, i_clean, target_t, target_v, design, cond, states, cfg["objective"])
        row = {
            "case_id": case_id,
            "split": split,
            "file_path": str(file_path.relative_to(out_root)),
            "family": cond.family,
            **{f"design__{k}": v for k, v in design.items()},
            **{f"truth__{k}": v for k, v in truth.items()},
            **{f"cond__{k}": v for k, v in asdict(cond).items()},
            **{f"meta__{k}": v for k, v in design_meta.items()},
            **{f"metric__{k}": v for k, v in metrics.items()},
        }
        index_rows.append(row)

    index_df = pd.DataFrame(index_rows)
    index_df.to_csv(base_dir / "index.csv", index=False)
    return {
        "n_cases": int(n_total),
        "splits": counts,
        "index": str((base_dir / "index.csv").relative_to(out_root)),
    }


def generate_identification_icp(repo_root: Path, out_root: Path, n_total: int = 80, seed: int = 20260315) -> Dict[str, Any]:
    rng = _rng(seed + 1)
    cfg = load_yaml(repo_root / "configs" / "design_space_icp_bias.yaml")
    target_t, target_v = load_target_waveform(repo_root / cfg["target_waveform"])
    design_space = cfg["design_space"]
    counts = _split_counts(n_total, (0.60, 0.15, 0.125, 0.125))
    split_labels = _basic_split_labels(n_total, counts)

    base_dir = out_root / "icp_bias_identification"
    _ensure_clean_dir(base_dir)
    for s in counts.keys():
        (base_dir / s).mkdir(parents=True, exist_ok=True)

    index_rows = []
    for i in range(n_total):
        split = split_labels[i]
        family = "nominal" if split != "test_ood" else "ood_nonlin"
        cond = _make_icp_condition(seed + 2000 + i, family)
        design = sample_space(design_space, rng)
        if split == "test_ood":
            design["COIL_FEED_LEN_M"] = float(min(4.0, max(0.2, design["COIL_FEED_LEN_M"] * 1.15)))
            design["BIAS_FEED_LEN_M"] = float(min(4.0, max(0.2, design["BIAS_FEED_LEN_M"] * 1.15)))

        t = target_t.copy()
        v_src_coil, v_coil_clean, v_bias_clean, design_meta = _make_icp_bias_port_voltages(t, design, target_v, cond)
        truth = _icp_truth_params_from_condition(cond, rng)
        i_coil_clean, i_bias_clean, states = _hidden_icp_bias_currents(t, v_coil_clean, v_bias_clean, truth, cond)
        v_coil_meas = _add_measurement_noise(v_coil_clean, cond.noise_level_v, rng)
        i_coil_meas = _add_measurement_noise(i_coil_clean, cond.noise_level_i, rng)
        v_bias_meas = _add_measurement_noise(v_bias_clean, cond.noise_level_v, rng)
        i_bias_meas = _add_measurement_noise(i_bias_clean, cond.noise_level_i, rng)

        case_id = f"icp_id_{i:04d}"
        file_path = base_dir / split / f"{case_id}.csv"
        rows = zip(
            t, v_coil_meas, i_coil_meas, v_bias_meas, i_bias_meas,
            v_coil_clean, i_coil_clean, v_bias_clean, i_bias_clean,
            v_src_coil, states["density_state"], states["heating_state"]
        )
        write_csv(
            file_path,
            ["time", "v_coil", "i_coil", "v_bias", "i_bias", "v_coil_clean", "i_coil_clean", "v_bias_clean", "i_bias_clean", "v_coil_src", "density_state", "heating_state"],
            rows,
        )

        metrics = _icp_case_metrics(t, v_coil_clean, i_coil_clean, v_bias_clean, i_bias_clean, target_t, target_v, design, cond, states, cfg["objective"])
        row = {
            "case_id": case_id,
            "split": split,
            "file_path": str(file_path.relative_to(out_root)),
            "family": cond.family,
            **{f"design__{k}": v for k, v in design.items()},
            **{f"truth__{k}": v for k, v in truth.items()},
            **{f"cond__{k}": v for k, v in asdict(cond).items()},
            **{f"meta__{k}": v for k, v in design_meta.items()},
            **{f"metric__{k}": v for k, v in metrics.items()},
        }
        index_rows.append(row)

    index_df = pd.DataFrame(index_rows)
    index_df.to_csv(base_dir / "index.csv", index=False)
    return {
        "n_cases": int(n_total),
        "splits": counts,
        "index": str((base_dir / "index.csv").relative_to(out_root)),
    }


def generate_codesign_ccp(repo_root: Path, out_root: Path, n_designs: int = 80, n_scenarios: int = 4, seed: int = 20260315) -> Dict[str, Any]:
    rng = _rng(seed + 10)
    cfg = load_yaml(repo_root / "configs" / "design_space_ccp.yaml")
    target_t, target_v = load_target_waveform(repo_root / cfg["target_waveform"])
    design_space = cfg["design_space"]
    objective_cfg = cfg["objective"]

    base_dir = out_root / "ccp_codesign"
    _ensure_clean_dir(base_dir)

    scenario_families = ["nominal", "nominal", "shifted_surface", "ood_nonlin"]
    assert len(scenario_families) == n_scenarios

    case_rows = []
    trace_rows = []
    agg_rows = []

    design_split_counts = _split_counts(n_designs, (0.625, 0.1875, 0.1875, 0.0))
    design_split_labels = []
    for k in ["train", "val", "test_id"]:
        design_split_labels.extend([k] * design_split_counts[k])

    for d_idx in range(n_designs):
        design_id = f"ccp_design_{d_idx:03d}"
        design_split = design_split_labels[d_idx]
        design = sample_space(design_space, rng)
        design_case_metrics = []
        for s_idx, family in enumerate(scenario_families):
            cond = _make_ccp_condition(seed + 3000 + 31 * d_idx + s_idx, family)
            t = target_t.copy()
            v_src, v_port_clean, design_meta = _make_ccp_port_voltage(t, design, target_v, cond)
            truth = _ccp_truth_params_from_condition(cond, rng)
            i_clean, states = _hidden_ccp_current(t, v_port_clean, v_src, truth, cond)

            case_id = f"{design_id}__scen_{s_idx}"
            metrics = _ccp_case_metrics(t, v_port_clean, i_clean, target_t, target_v, design, cond, states, objective_cfg)
            design_case_metrics.append(metrics["objective"])
            row = {
                "case_id": case_id,
                "design_id": design_id,
                "design_split": design_split,
                "scenario_id": s_idx,
                "scenario_family": family,
                **design,
                **{f"cond__{k}": v for k, v in asdict(cond).items()},
                **{f"truth__{k}": v for k, v in truth.items()},
                **{f"meta__{k}": v for k, v in design_meta.items()},
                **metrics,
            }
            case_rows.append(row)

            for k in range(len(t)):
                trace_rows.append({
                    "case_id": case_id,
                    "design_id": design_id,
                    "scenario_id": s_idx,
                    "time": float(t[k]),
                    "v_port": float(v_port_clean[k]),
                    "i_port": float(i_clean[k]),
                    "v_src": float(v_src[k]),
                    "density_state": float(states["density_state"][k]),
                    "asym_state": float(states["asym_state"][k]),
                })

        arr = np.array(design_case_metrics, dtype=float)
        agg_rows.append({
            "design_id": design_id,
            "design_split": design_split,
            **design,
            "mean_objective": float(np.mean(arr)),
            "std_objective": float(np.std(arr, ddof=0)),
            "robust_objective": float(np.mean(arr) + 0.35 * np.std(arr, ddof=0)),
            "n_scenarios": int(n_scenarios),
        })

    pd.DataFrame(case_rows).to_csv(base_dir / "ccp_cases.csv", index=False)
    pd.DataFrame(agg_rows).to_csv(base_dir / "ccp_design_aggregates.csv", index=False)
    pd.DataFrame(trace_rows).to_csv(base_dir / "ccp_traces.csv.gz", index=False, compression="gzip")

    return {
        "n_designs": int(n_designs),
        "n_scenarios_per_design": int(n_scenarios),
        "n_cases": int(n_designs * n_scenarios),
        "cases": str((base_dir / "ccp_cases.csv").relative_to(out_root)),
        "aggregates": str((base_dir / "ccp_design_aggregates.csv").relative_to(out_root)),
        "traces": str((base_dir / "ccp_traces.csv.gz").relative_to(out_root)),
    }


def generate_codesign_icp(repo_root: Path, out_root: Path, n_designs: int = 64, n_scenarios: int = 4, seed: int = 20260315) -> Dict[str, Any]:
    rng = _rng(seed + 11)
    cfg = load_yaml(repo_root / "configs" / "design_space_icp_bias.yaml")
    target_t, target_v = load_target_waveform(repo_root / cfg["target_waveform"])
    design_space = cfg["design_space"]
    objective_cfg = cfg["objective"]

    base_dir = out_root / "icp_bias_codesign"
    _ensure_clean_dir(base_dir)

    scenario_families = ["nominal", "nominal", "shifted_surface", "ood_nonlin"]
    assert len(scenario_families) == n_scenarios

    case_rows = []
    trace_rows = []
    agg_rows = []

    design_split_counts = _split_counts(n_designs, (0.625, 0.1875, 0.1875, 0.0))
    design_split_labels = []
    for k in ["train", "val", "test_id"]:
        design_split_labels.extend([k] * design_split_counts[k])

    for d_idx in range(n_designs):
        design_id = f"icp_design_{d_idx:03d}"
        design_split = design_split_labels[d_idx]
        design = sample_space(design_space, rng)
        design_case_metrics = []
        for s_idx, family in enumerate(scenario_families):
            cond = _make_icp_condition(seed + 4000 + 37 * d_idx + s_idx, family)
            t = target_t.copy()
            v_src_coil, v_coil_clean, v_bias_clean, design_meta = _make_icp_bias_port_voltages(t, design, target_v, cond)
            truth = _icp_truth_params_from_condition(cond, rng)
            i_coil_clean, i_bias_clean, states = _hidden_icp_bias_currents(t, v_coil_clean, v_bias_clean, truth, cond)

            case_id = f"{design_id}__scen_{s_idx}"
            metrics = _icp_case_metrics(t, v_coil_clean, i_coil_clean, v_bias_clean, i_bias_clean, target_t, target_v, design, cond, states, objective_cfg)
            design_case_metrics.append(metrics["objective"])
            row = {
                "case_id": case_id,
                "design_id": design_id,
                "design_split": design_split,
                "scenario_id": s_idx,
                "scenario_family": family,
                **design,
                **{f"cond__{k}": v for k, v in asdict(cond).items()},
                **{f"truth__{k}": v for k, v in truth.items()},
                **{f"meta__{k}": v for k, v in design_meta.items()},
                **metrics,
            }
            case_rows.append(row)

            for k in range(len(t)):
                trace_rows.append({
                    "case_id": case_id,
                    "design_id": design_id,
                    "scenario_id": s_idx,
                    "time": float(t[k]),
                    "v_coil": float(v_coil_clean[k]),
                    "i_coil": float(i_coil_clean[k]),
                    "v_bias": float(v_bias_clean[k]),
                    "i_bias": float(i_bias_clean[k]),
                    "v_src_coil": float(v_src_coil[k]),
                    "density_state": float(states["density_state"][k]),
                    "heating_state": float(states["heating_state"][k]),
                })

        arr = np.array(design_case_metrics, dtype=float)
        agg_rows.append({
            "design_id": design_id,
            "design_split": design_split,
            **design,
            "mean_objective": float(np.mean(arr)),
            "std_objective": float(np.std(arr, ddof=0)),
            "robust_objective": float(np.mean(arr) + 0.35 * np.std(arr, ddof=0)),
            "n_scenarios": int(n_scenarios),
        })

    pd.DataFrame(case_rows).to_csv(base_dir / "icp_bias_cases.csv", index=False)
    pd.DataFrame(agg_rows).to_csv(base_dir / "icp_bias_design_aggregates.csv", index=False)
    pd.DataFrame(trace_rows).to_csv(base_dir / "icp_bias_traces.csv.gz", index=False, compression="gzip")

    return {
        "n_designs": int(n_designs),
        "n_scenarios_per_design": int(n_scenarios),
        "n_cases": int(n_designs * n_scenarios),
        "cases": str((base_dir / "icp_bias_cases.csv").relative_to(out_root)),
        "aggregates": str((base_dir / "icp_bias_design_aggregates.csv").relative_to(out_root)),
        "traces": str((base_dir / "icp_bias_traces.csv.gz").relative_to(out_root)),
    }


def _write_benchmark_readme(out_root: Path) -> None:
    text = """# plasma_codesign synthetic benchmark

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
"""
    (out_root / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out-root", type=Path, default=Path(__file__).resolve().parents[1] / "benchmark")
    parser.add_argument("--seed", type=int, default=20260315)
    parser.add_argument("--ccp-id-cases", type=int, default=96)
    parser.add_argument("--icp-id-cases", type=int, default=80)
    parser.add_argument("--ccp-designs", type=int, default=80)
    parser.add_argument("--icp-designs", type=int, default=64)
    args = parser.parse_args()

    out_root = args.out_root
    _ensure_clean_dir(out_root)

    # Ensure default targets exist in repo data/.
    data_dir = args.repo_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    t_ccp, v_ccp = None, None
    ccp_cfg = load_yaml(args.repo_root / "configs" / "design_space_ccp.yaml")
    icp_cfg = load_yaml(args.repo_root / "configs" / "design_space_icp_bias.yaml")
    t_ccp = np.arange(0.0, float(ccp_cfg["design_space"]["TSTOP"]["value"]) + 0.5 * float(ccp_cfg["design_space"]["TSTEP"]["value"]), float(ccp_cfg["design_space"]["TSTEP"]["value"]))
    v_ccp = make_ccp_target(t_ccp, float(ccp_cfg["design_space"]["F_BIAS"]["value"]))
    write_csv(data_dir / "target_ccp_waveform.csv", ["time", "v_target"], zip(t_ccp, v_ccp))
    t_bias = np.arange(0.0, float(icp_cfg["design_space"]["TSTOP"]["value"]) + 0.5 * float(icp_cfg["design_space"]["TSTEP"]["value"]), float(icp_cfg["design_space"]["TSTEP"]["value"]))
    v_bias = make_bias_target(t_bias, float(icp_cfg["design_space"]["F_BIAS"]["value"]))
    write_csv(data_dir / "target_bias_waveform.csv", ["time", "v_target"], zip(t_bias, v_bias))

    manifest = {
        "name": "plasma_codesign_synthetic_benchmark",
        "seed": args.seed,
        "repo_root": str(args.repo_root),
        "artifacts": {},
    }
    manifest["artifacts"]["ccp_identification"] = generate_identification_ccp(args.repo_root, out_root, n_total=args.ccp_id_cases, seed=args.seed)
    manifest["artifacts"]["icp_bias_identification"] = generate_identification_icp(args.repo_root, out_root, n_total=args.icp_id_cases, seed=args.seed)
    manifest["artifacts"]["ccp_codesign"] = generate_codesign_ccp(args.repo_root, out_root, n_designs=args.ccp_designs, seed=args.seed)
    manifest["artifacts"]["icp_bias_codesign"] = generate_codesign_icp(args.repo_root, out_root, n_designs=args.icp_designs, seed=args.seed)
    save_json(manifest, out_root / "manifest.json")
    _write_benchmark_readme(out_root)
    print(f"Wrote benchmark to {out_root}")


if __name__ == "__main__":
    main()
