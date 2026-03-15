#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

import schemdraw
import schemdraw.elements as elm
import skrf as rf
from skrf.plotting import smith as rf_smith


SPLIT_ORDER = ["train", "val", "test_id", "test_ood"]
SCENARIO_ORDER = ["nominal", "shifted_surface", "ood_nonlin"]
Z0_DEFAULT = 50.0


def _ecdf(x: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return np.array([]), np.array([])
    x = np.sort(x)
    y = np.arange(1, x.size + 1, dtype=float) / float(x.size)
    return x, y


def _bootstrap_mean_ci(x: np.ndarray, n_boot: int = 2000, seed: int = 7) -> Tuple[float, float, float]:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot, dtype=float)
    n = x.size
    for i in range(n_boot):
        s = x[rng.integers(0, n, size=n)]
        means[i] = float(np.mean(s))
    mean = float(np.mean(x))
    lo, hi = np.quantile(means, [0.025, 0.975])
    return mean, float(lo), float(hi)


def _pareto_mask_minimize(df: pd.DataFrame, xcol: str, ycol: str) -> np.ndarray:
    pts = df[[xcol, ycol]].to_numpy(dtype=float)
    n = pts.shape[0]
    mask = np.ones(n, dtype=bool)
    for i in range(n):
        if not mask[i]:
            continue
        dominated = (pts[:, 0] <= pts[i, 0]) & (pts[:, 1] <= pts[i, 1]) & ((pts[:, 0] < pts[i, 0]) | (pts[:, 1] < pts[i, 1]))
        dominated[i] = False
        if np.any(dominated):
            mask[i] = False
    return mask


def _load(benchmark_root: Path, repo_root: Path) -> Dict[str, pd.DataFrame]:
    return {
        "ccp_agg": pd.read_csv(benchmark_root / "ccp_codesign" / "ccp_design_aggregates.csv"),
        "icp_agg": pd.read_csv(benchmark_root / "icp_bias_codesign" / "icp_bias_design_aggregates.csv"),
        "ccp_cases": pd.read_csv(benchmark_root / "ccp_codesign" / "ccp_cases.csv"),
        "icp_cases": pd.read_csv(benchmark_root / "icp_bias_codesign" / "icp_bias_cases.csv"),
        "ccp_tr": pd.read_csv(benchmark_root / "ccp_codesign" / "ccp_traces.csv.gz"),
        "icp_tr": pd.read_csv(benchmark_root / "icp_bias_codesign" / "icp_bias_traces.csv.gz"),
        "ccp_base": pd.read_csv(benchmark_root / "baselines" / "ccp_identification_baseline.csv"),
        "icp_base": pd.read_csv(benchmark_root / "baselines" / "icp_identification_baseline.csv"),
        "target_ccp": pd.read_csv(repo_root / "data" / "target_ccp_waveform.csv"),
        "target_bias": pd.read_csv(repo_root / "data" / "target_bias_waveform.csv"),
    }


def _fmt_eng(v: float) -> str:
    if v == 0:
        return "0"
    p = int(np.floor(np.log10(abs(v)) / 3) * 3)
    p = max(min(p, 9), -12)
    scale = 10.0 ** p
    s = v / scale
    suf = {
        -12: "p",
        -9: "n",
        -6: "u",
        -3: "m",
        0: "",
        3: "k",
        6: "M",
        9: "G",
    }[p]
    return f"{s:.3g}{suf}"


def _phasor_fundamental(t: np.ndarray, y: np.ndarray, f_hz: float) -> complex:
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    w = 2.0 * np.pi * float(f_hz)
    cos_c = 2.0 * np.mean(y * np.cos(w * t))
    sin_c = 2.0 * np.mean(y * np.sin(w * t))
    return complex(cos_c, -sin_c)


def _collect_impedance_points(
    cases: pd.DataFrame,
    traces: pd.DataFrame,
    freq_col: str,
    v_col: str,
    i_col: str,
    z0: float,
) -> pd.DataFrame:
    rows = []
    for case_id, tr in traces.groupby("case_id"):
        meta = cases[cases["case_id"] == case_id]
        if len(meta) == 0:
            continue
        m = meta.iloc[0]
        t = tr["time"].to_numpy(dtype=float)
        v = tr[v_col].to_numpy(dtype=float)
        i = tr[i_col].to_numpy(dtype=float)
        f_hz = float(m[freq_col])
        v1 = _phasor_fundamental(t, v, f_hz)
        i1 = _phasor_fundamental(t, i, f_hz)
        if abs(i1) < 1e-15:
            continue
        z = v1 / i1
        z_norm = z / float(z0)
        gamma = (z_norm - 1.0) / (z_norm + 1.0)
        rows.append(
            {
                "case_id": str(case_id),
                "design_id": str(m["design_id"]),
                "scenario_family": str(m["scenario_family"]),
                "design_split": str(m["design_split"]),
                "freq_hz": f_hz,
                "Z_real": float(np.real(z)),
                "Z_imag": float(np.imag(z)),
                "Gamma_real": float(np.real(gamma)),
                "Gamma_imag": float(np.imag(gamma)),
                "Gamma_mag": float(abs(gamma)),
                "return_loss_db": float(-20.0 * np.log10(max(abs(gamma), 1e-12))),
                "vswr": float((1.0 + abs(gamma)) / max(1.0 - abs(gamma), 1e-9)),
            }
        )
    return pd.DataFrame(rows)


def _draw_ccp_schematic(best: pd.Series, out_svg: Path, out_png: Path) -> List[Path]:
    vac = float(best["VAC_BIAS"])
    f = float(best["F_BIAS"])
    topo = str(best["topology"])
    rgen = float(best["R_GEN"])
    l = float(best["L_MATCH"])
    cmout = float(best["C_MATCH_OUT"])
    cmin = float(best["C_MATCH_IN"])
    cblock = float(best["C_BLOCK"])
    rcab = float(best["CABLE_R_PER_M"] * best["CABLE_LEN_M"])
    lcab = float(best["CABLE_L_PER_M"] * best["CABLE_LEN_M"])
    ccab = float(best["CABLE_C_PER_M"] * best["CABLE_LEN_M"])
    rret = float(best["RETURN_R_PER_M"] * best["RETURN_LEN_M"])
    lret = float(best["RETURN_L_PER_M"] * best["RETURN_LEN_M"])

    d = schemdraw.Drawing(show=False)
    d.config(unit=2.0, fontsize=10)
    d += elm.SourceSin().label(f"Vsrc\\n{vac:.1f} V\\n{f/1e6:.3g} MHz")
    d += elm.Resistor().right().label(f"Rgen\\n{_fmt_eng(rgen)}Ω")

    if topo == "PI":
        n0 = d.here
        d += elm.Line().right()
        n1 = d.here
        d.push()
        d += elm.Capacitor().down().at(n0).label(f"Cin\\n{_fmt_eng(cmin)}F")
        d += elm.Ground()
        d.pop()
        d += elm.Inductor().right().label(f"Lmatch\\n{_fmt_eng(l)}H")
        n2 = d.here
        d.push()
        d += elm.Capacitor().down().at(n2).label(f"Cout\\n{_fmt_eng(cmout)}F")
        d += elm.Ground()
        d.pop()
    else:
        d += elm.Inductor().right().label(f"Lmatch\\n{_fmt_eng(l)}H")
        n2 = d.here
        d.push()
        d += elm.Capacitor().down().at(n2).label(f"Cout\\n{_fmt_eng(cmout)}F")
        d += elm.Ground()
        d.pop()

    d += elm.Resistor().right().label(f"Rcable\\n{_fmt_eng(rcab)}Ω")
    d += elm.Inductor().right().label(f"Lcable\\n{_fmt_eng(lcab)}H")
    n3 = d.here
    d.push()
    d += elm.Capacitor().down().at(n3).label(f"Ccable\\n{_fmt_eng(ccab)}F")
    d += elm.Ground()
    d.pop()
    d += elm.Capacitor().right().label(f"Cblock\\n{_fmt_eng(cblock)}F")

    n4 = d.here
    d.push()
    d += elm.Resistor().down().at(n4).label("Rplasma\\n90Ω")
    d += elm.Ground()
    d.pop()
    d.push()
    d += elm.Capacitor().down().at(n4).label("Cplasma\\n35pF")
    d += elm.Ground()
    d.pop()
    d.push()
    d += elm.Resistor().down().at(n4).label(f"Rreturn\\n{_fmt_eng(rret)}Ω")
    d += elm.Inductor().down().label(f"Lreturn\\n{_fmt_eng(lret)}H")
    d += elm.Ground()
    d.pop()

    out_svg.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(out_svg))
    outs = [out_svg]
    try:
        d.save(str(out_png), dpi=220)
        outs.append(out_png)
    except Exception:
        pass
    return outs


def _draw_icp_schematic(best: pd.Series, out_svg: Path, out_png: Path) -> List[Path]:
    f_icp = float(best["F_ICP"])
    f_bias = float(best["F_BIAS"])
    vicp = float(best["VICP_AC"])
    vbias = float(best["VBIAS_AC"])
    vdc = float(best["VBIAS_DC"])

    r_icp = float(best["R_ICP_GEN"])
    r_bias = float(best["R_BIAS_GEN"])
    l_coil = float(best["L_COIL_MATCH"])
    l_bias = float(best["L_BIAS_MATCH"])
    c_coil = float(best["C_COIL_MATCH_OUT"])
    c_bias = float(best["C_BIAS_MATCH_OUT"])
    cblock = float(best["C_BLOCK_BIAS"])

    d = schemdraw.Drawing(show=False)
    d.config(unit=1.9, fontsize=10)

    # Coil branch
    d += elm.SourceSin().label(f"ICP Src\\n{vicp:.1f}V\\n{f_icp/1e6:.3g}MHz")
    d += elm.Resistor().right().label(f"Rgen\\n{_fmt_eng(r_icp)}Ω")
    d += elm.Inductor().right().label(f"Lcoil\\n{_fmt_eng(l_coil)}H")
    n_coil = d.here
    d.push()
    d += elm.Capacitor().down().at(n_coil).label(f"Ccoil\\n{_fmt_eng(c_coil)}F")
    d += elm.Ground()
    d.pop()
    d += elm.Resistor().right().label("Plasma coil\\n0.8Ω")
    d += elm.Ground()

    # Bias branch
    d.move(dy=-5.0)
    d += elm.SourceSin().label(f"Bias Src\\n{vbias:.1f}V AC\\n{vdc:.1f}V DC\\n{f_bias/1e6:.3g}MHz")
    d += elm.Resistor().right().label(f"Rgen\\n{_fmt_eng(r_bias)}Ω")
    d += elm.Inductor().right().label(f"Lbias\\n{_fmt_eng(l_bias)}H")
    n_bias = d.here
    d.push()
    d += elm.Capacitor().down().at(n_bias).label(f"Cbias\\n{_fmt_eng(c_bias)}F")
    d += elm.Ground()
    d.pop()
    d += elm.Capacitor().right().label(f"Cblock\\n{_fmt_eng(cblock)}F")
    n_pl = d.here
    d.push()
    d += elm.Resistor().down().at(n_pl).label("Rplasma\\n120Ω")
    d += elm.Ground()
    d.pop()
    d.push()
    d += elm.Capacitor().down().at(n_pl).label("Cplasma\\n42pF")
    d += elm.Ground()
    d.pop()

    out_svg.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(out_svg))
    outs = [out_svg]
    try:
        d.save(str(out_png), dpi=220)
        outs.append(out_png)
    except Exception:
        pass
    return outs


def plot_schemdraw_circuits(data: Dict[str, pd.DataFrame], outdir: Path) -> List[Path]:
    ccp_best = data["ccp_agg"].sort_values("robust_objective").iloc[0]
    icp_best = data["icp_agg"].sort_values("robust_objective").iloc[0]
    outs: List[Path] = []
    outs.extend(
        _draw_ccp_schematic(
            ccp_best,
            outdir / "deep_ccp_schematic_schemdraw.svg",
            outdir / "deep_ccp_schematic_schemdraw.png",
        )
    )
    outs.extend(
        _draw_icp_schematic(
            icp_best,
            outdir / "deep_icp_bias_schematic_schemdraw.svg",
            outdir / "deep_icp_bias_schematic_schemdraw.png",
        )
    )
    return outs


def plot_smith_and_rf_metrics(
    data: Dict[str, pd.DataFrame],
    outdir: Path,
    z0: float = Z0_DEFAULT,
) -> Tuple[List[Path], Dict[str, Dict[str, float]]]:
    ccp_pts = _collect_impedance_points(data["ccp_cases"], data["ccp_tr"], "F_BIAS", "v_port", "i_port", z0=z0)
    icp_pts = _collect_impedance_points(data["icp_cases"], data["icp_tr"], "F_BIAS", "v_bias", "i_bias", z0=z0)

    out_paths: List[Path] = []

    # Smith charts
    fig, axes = plt.subplots(1, 2, figsize=(13, 6), constrained_layout=True)
    for ax, df, title in [
        (axes[0], ccp_pts, "CCP Smith chart (fundamental impedance)"),
        (axes[1], icp_pts, "ICP+Bias Smith chart (bias port)"),
    ]:
        rf_smith(ax=ax, smithR=1.0, chart_type="z", draw_labels=False, border=True)
        for fam in SCENARIO_ORDER:
            sub = df[df["scenario_family"] == fam]
            if len(sub) == 0:
                continue
            ax.scatter(sub["Gamma_real"], sub["Gamma_imag"], s=24, alpha=0.78, label=fam)
        ax.set_title(title)
        ax.legend(loc="upper right", fontsize=8)
    smith_path = outdir / "deep_smith_charts.png"
    fig.savefig(smith_path, dpi=200)
    plt.close(fig)
    out_paths.append(smith_path)

    # Impedance complex plane
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), constrained_layout=True)
    for ax, df, title in [
        (axes[0], ccp_pts, "CCP impedance plane"),
        (axes[1], icp_pts, "ICP+Bias bias-port impedance plane"),
    ]:
        sns.scatterplot(data=df, x="Z_real", y="Z_imag", hue="scenario_family", hue_order=SCENARIO_ORDER, s=34, alpha=0.8, ax=ax)
        ax.axhline(0.0, color="#6b7280", lw=1.0)
        ax.axvline(z0, color="#9ca3af", lw=1.0, ls="--")
        ax.set_title(title)
        ax.set_xlabel("Re{Z} [ohm]")
        ax.set_ylabel("Im{Z} [ohm]")
        ax.grid(True, alpha=0.25)
        ax.legend(loc="best", fontsize=8)
    zplane = outdir / "deep_impedance_plane.png"
    fig.savefig(zplane, dpi=200)
    plt.close(fig)
    out_paths.append(zplane)

    # Return loss distribution
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), constrained_layout=True)
    for ax, df, title in [
        (axes[0], ccp_pts, "CCP return loss by scenario"),
        (axes[1], icp_pts, "ICP+Bias return loss by scenario"),
    ]:
        sns.boxplot(data=df, x="scenario_family", y="return_loss_db", order=SCENARIO_ORDER, ax=ax, fliersize=2)
        ax.set_title(title)
        ax.set_xlabel("scenario_family")
        ax.set_ylabel("Return Loss [dB]")
        ax.grid(True, axis="y", alpha=0.25)
    rl_path = outdir / "deep_return_loss_distribution.png"
    fig.savefig(rl_path, dpi=200)
    plt.close(fig)
    out_paths.append(rl_path)

    stats = {
        "ccp": {
            "gamma_mag_mean": float(ccp_pts["Gamma_mag"].mean()),
            "gamma_mag_q90": float(ccp_pts["Gamma_mag"].quantile(0.9)),
            "return_loss_mean_db": float(ccp_pts["return_loss_db"].mean()),
        },
        "icp_bias": {
            "gamma_mag_mean": float(icp_pts["Gamma_mag"].mean()),
            "gamma_mag_q90": float(icp_pts["Gamma_mag"].quantile(0.9)),
            "return_loss_mean_db": float(icp_pts["return_loss_db"].mean()),
        },
        "ccp_by_scenario_return_loss_db": {
            k: float(v) for k, v in ccp_pts.groupby("scenario_family")["return_loss_db"].mean().to_dict().items()
        },
        "icp_by_scenario_return_loss_db": {
            k: float(v) for k, v in icp_pts.groupby("scenario_family")["return_loss_db"].mean().to_dict().items()
        },
    }
    return out_paths, stats


def plot_baseline_ecdf(data: Dict[str, pd.DataFrame], outdir: Path) -> Path:
    ccp = data["ccp_base"]
    icp = data["icp_base"]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    settings = [
        (axes[0, 0], ccp, "nrmse_meas", "CCP nrmse_meas"),
        (axes[0, 1], ccp, "nrmse_clean", "CCP nrmse_clean"),
        (axes[1, 0], icp, "coil_nrmse_meas", "ICP coil_nrmse_meas"),
        (axes[1, 1], icp, "bias_nrmse_meas", "ICP bias_nrmse_meas"),
    ]
    palette = sns.color_palette("tab10", n_colors=4)

    for ax, df, metric, title in settings:
        for i, split in enumerate(SPLIT_ORDER):
            sub = df[df["split"] == split]
            if len(sub) == 0:
                continue
            x, y = _ecdf(sub[metric].to_numpy())
            ax.plot(x, y, lw=1.8, color=palette[i], label=f"{split} (n={len(sub)})")
        ax.set_title(title)
        ax.set_xlabel(metric)
        ax.set_ylabel("ECDF")
        ax.grid(True, alpha=0.25)
        ax.legend(loc="lower right", fontsize=9)

    out = outdir / "deep_baseline_ecdf.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_baseline_split_hist(data: Dict[str, pd.DataFrame], outdir: Path) -> Path:
    ccp = data["ccp_base"]
    icp = data["icp_base"]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.2), constrained_layout=True)

    sns.histplot(
        data=ccp,
        x="nrmse_meas",
        hue="split",
        hue_order=[s for s in SPLIT_ORDER if s in set(ccp["split"])],
        stat="density",
        common_norm=False,
        bins=18,
        element="step",
        fill=False,
        ax=axes[0],
    )
    axes[0].set_title("CCP nrmse_meas distribution by split")
    axes[0].grid(True, alpha=0.25)

    sns.histplot(
        data=icp,
        x="bias_nrmse_meas",
        hue="split",
        hue_order=[s for s in SPLIT_ORDER if s in set(icp["split"])],
        stat="density",
        common_norm=False,
        bins=18,
        element="step",
        fill=False,
        ax=axes[1],
    )
    axes[1].set_title("ICP bias_nrmse_meas distribution by split")
    axes[1].grid(True, alpha=0.25)

    out = outdir / "deep_baseline_split_hist.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_id_ood_ci(data: Dict[str, pd.DataFrame], outdir: Path) -> Tuple[Path, pd.DataFrame]:
    ccp = data["ccp_base"].copy()
    icp = data["icp_base"].copy()
    ccp["group"] = np.where(ccp["split"] == "test_ood", "ood", "id")
    icp["group"] = np.where(icp["split"] == "test_ood", "ood", "id")

    rows = []
    specs = [
        ("CCP", ccp, "nrmse_meas"),
        ("CCP", ccp, "nrmse_clean"),
        ("ICP+Bias", icp, "coil_nrmse_meas"),
        ("ICP+Bias", icp, "bias_nrmse_meas"),
    ]
    for prob, df, metric in specs:
        for group in ["id", "ood"]:
            vals = df[df["group"] == group][metric].to_numpy(dtype=float)
            mean, lo, hi = _bootstrap_mean_ci(vals)
            rows.append({"problem": prob, "metric": metric, "group": group, "mean": mean, "ci_lo": lo, "ci_hi": hi})

    table = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(12, 6), constrained_layout=True)
    plot_df = table.copy()
    plot_df["label"] = plot_df["problem"] + "\n" + plot_df["metric"]

    x_labels = list(dict.fromkeys(plot_df["label"].tolist()))
    x_pos = np.arange(len(x_labels), dtype=float)
    width = 0.32
    offset = {"id": -width / 2.0, "ood": width / 2.0}
    color = {"id": "#2563eb", "ood": "#dc2626"}

    for g in ["id", "ood"]:
        sub = plot_df[plot_df["group"] == g]
        xs = np.array([x_pos[x_labels.index(lbl)] + offset[g] for lbl in sub["label"]])
        y = sub["mean"].to_numpy()
        lo = y - sub["ci_lo"].to_numpy()
        hi = sub["ci_hi"].to_numpy() - y
        ax.bar(xs, y, width=width, color=color[g], alpha=0.85, label=g)
        ax.errorbar(xs, y, yerr=np.vstack([lo, hi]), fmt="none", ecolor="#111827", elinewidth=1.2, capsize=3)

    ax.set_xticks(x_pos)
    ax.set_xticklabels(x_labels, fontsize=9)
    ax.set_ylabel("mean error (with 95% bootstrap CI)")
    ax.set_title("ID vs OOD comparison with uncertainty")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(loc="upper left")

    out = outdir / "deep_id_ood_ci.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out, table


def plot_robust_split_violin(data: Dict[str, pd.DataFrame], outdir: Path) -> Tuple[Path, Dict[str, Dict[str, float]]]:
    ccp = data["ccp_agg"].copy()
    icp = data["icp_agg"].copy()
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.6), constrained_layout=True)

    for ax, df, title in [
        (axes[0], ccp, "CCP robust objective by design split"),
        (axes[1], icp, "ICP+Bias robust objective by design split"),
    ]:
        order = [s for s in SPLIT_ORDER if s in set(df["design_split"])]
        sns.violinplot(data=df, x="design_split", y="robust_objective", order=order, inner=None, cut=0, ax=ax, color="#bfdbfe")
        sns.boxplot(
            data=df,
            x="design_split",
            y="robust_objective",
            order=order,
            width=0.28,
            showcaps=True,
            boxprops={"facecolor": "white", "zorder": 3},
            showfliers=False,
            whiskerprops={"linewidth": 1.1},
            ax=ax,
        )
        ax.set_title(title)
        ax.set_xlabel("design_split")
        ax.set_ylabel("robust_objective")
        ax.grid(True, axis="y", alpha=0.25)

    out = outdir / "deep_robust_split_violin.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)

    split_stats: Dict[str, Dict[str, float]] = {}
    for name, df in [("ccp", ccp), ("icp_bias", icp)]:
        rows = {}
        for split, g in df.groupby("design_split"):
            rows[str(split)] = float(g["robust_objective"].mean())
        split_stats[name] = rows
    return out, split_stats


def plot_pareto_frontier(data: Dict[str, pd.DataFrame], outdir: Path) -> Tuple[Path, Dict[str, int]]:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), constrained_layout=True)
    counts: Dict[str, int] = {}

    for ax, key, title in [
        (axes[0], "ccp_agg", "CCP Pareto frontier (min mean, min std)"),
        (axes[1], "icp_agg", "ICP+Bias Pareto frontier (min mean, min std)"),
    ]:
        df = data[key].copy()
        mask = _pareto_mask_minimize(df, "mean_objective", "std_objective")
        pareto = df[mask].sort_values("mean_objective")
        counts[key] = int(mask.sum())

        sns.scatterplot(
            data=df,
            x="mean_objective",
            y="std_objective",
            hue="design_split",
            hue_order=[s for s in SPLIT_ORDER if s in set(df["design_split"])],
            alpha=0.55,
            ax=ax,
            s=45,
        )
        ax.plot(pareto["mean_objective"], pareto["std_objective"], color="#111827", lw=2.0, label=f"pareto ({len(pareto)})")
        ax.scatter(pareto["mean_objective"], pareto["std_objective"], color="#111827", s=30)
        ax.set_title(title)
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper right")

    out = outdir / "deep_pareto_frontier.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out, counts


def plot_topology_effect(data: Dict[str, pd.DataFrame], outdir: Path) -> Tuple[Path, Dict[str, Dict[str, float]]]:
    ccp = data["ccp_agg"].copy()
    icp = data["icp_agg"].copy()
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5), constrained_layout=True)

    sns.boxplot(data=ccp, x="topology", y="robust_objective", order=["L", "PI"], ax=axes[0], fliersize=2.0)
    axes[0].set_title("CCP topology effect")
    axes[0].grid(True, axis="y", alpha=0.25)

    sns.boxplot(data=icp, x="coil_topology", y="robust_objective", order=["L", "PI"], ax=axes[1], fliersize=2.0)
    axes[1].set_title("ICP coil topology effect")
    axes[1].grid(True, axis="y", alpha=0.25)

    sns.boxplot(data=icp, x="bias_topology", y="robust_objective", order=["L", "PI"], ax=axes[2], fliersize=2.0)
    axes[2].set_title("ICP bias topology effect")
    axes[2].grid(True, axis="y", alpha=0.25)

    out = outdir / "deep_topology_effect.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)

    stats = {
        "ccp": {k: float(v) for k, v in ccp.groupby("topology")["robust_objective"].mean().to_dict().items()},
        "icp_coil": {k: float(v) for k, v in icp.groupby("coil_topology")["robust_objective"].mean().to_dict().items()},
        "icp_bias": {k: float(v) for k, v in icp.groupby("bias_topology")["robust_objective"].mean().to_dict().items()},
    }
    return out, stats


def plot_stability_index(data: Dict[str, pd.DataFrame], outdir: Path) -> Tuple[Path, Dict[str, Dict[str, float]]]:
    ccp = data["ccp_agg"].copy()
    icp = data["icp_agg"].copy()
    ccp["stability_ratio"] = ccp["std_objective"] / np.maximum(ccp["mean_objective"], 1e-12)
    icp["stability_ratio"] = icp["std_objective"] / np.maximum(icp["mean_objective"], 1e-12)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), constrained_layout=True)
    for ax, df, title in [
        (axes[0], ccp, "CCP stability ratio map"),
        (axes[1], icp, "ICP+Bias stability ratio map"),
    ]:
        sc = ax.scatter(
            df["mean_objective"],
            df["stability_ratio"],
            c=df["robust_objective"],
            cmap="viridis",
            s=48,
            alpha=0.85,
            edgecolor="none",
        )
        ax.set_title(title)
        ax.set_xlabel("mean_objective")
        ax.set_ylabel("std/mean")
        ax.grid(True, alpha=0.25)
        cbar = fig.colorbar(sc, ax=ax)
        cbar.set_label("robust_objective")

    out = outdir / "deep_stability_index.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)

    stats = {
        "ccp": {
            "stability_ratio_median": float(ccp["stability_ratio"].median()),
            "stability_ratio_q90": float(ccp["stability_ratio"].quantile(0.9)),
        },
        "icp_bias": {
            "stability_ratio_median": float(icp["stability_ratio"].median()),
            "stability_ratio_q90": float(icp["stability_ratio"].quantile(0.9)),
        },
    }
    return out, stats


def _rank_correlations(df: pd.DataFrame, target: str, extra_binary: Dict[str, pd.Series] | None = None) -> pd.Series:
    x = df.copy()
    if extra_binary:
        for k, v in extra_binary.items():
            x[k] = v
    num = x.select_dtypes(include=[np.number]).copy()
    if target not in num.columns:
        raise ValueError(target)

    corr = num.corr(method="spearman")[target].drop(labels=[target])
    keep = []
    for c in corr.index:
        if num[c].nunique(dropna=True) > 1:
            keep.append(c)
    corr = corr.loc[keep].dropna()
    corr = corr.reindex(corr.abs().sort_values(ascending=False).index)
    return corr


def plot_factor_correlation(data: Dict[str, pd.DataFrame], outdir: Path, top_k: int = 12) -> Tuple[Path, Dict[str, Dict[str, float]]]:
    ccp = data["ccp_agg"].copy()
    icp = data["icp_agg"].copy()

    ccp_corr = _rank_correlations(ccp, "robust_objective", {"topology_PI": (ccp["topology"] == "PI").astype(float)}).head(top_k)
    icp_corr = _rank_correlations(
        icp,
        "robust_objective",
        {
            "coil_topology_PI": (icp["coil_topology"] == "PI").astype(float),
            "bias_topology_PI": (icp["bias_topology"] == "PI").astype(float),
        },
    ).head(top_k)

    fig, axes = plt.subplots(1, 2, figsize=(15, 6), constrained_layout=True)

    axes[0].barh(ccp_corr.index[::-1], ccp_corr.values[::-1], color=np.where(ccp_corr.values[::-1] >= 0.0, "#2563eb", "#dc2626"))
    axes[0].set_title("CCP: top Spearman correlations with robust objective")
    axes[0].set_xlabel("Spearman rho")
    axes[0].grid(True, axis="x", alpha=0.25)

    axes[1].barh(icp_corr.index[::-1], icp_corr.values[::-1], color=np.where(icp_corr.values[::-1] >= 0.0, "#2563eb", "#dc2626"))
    axes[1].set_title("ICP+Bias: top Spearman correlations with robust objective")
    axes[1].set_xlabel("Spearman rho")
    axes[1].grid(True, axis="x", alpha=0.25)

    out = outdir / "deep_factor_correlation.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)

    top = {
        "ccp": {k: float(v) for k, v in ccp_corr.head(5).items()},
        "icp_bias": {k: float(v) for k, v in icp_corr.head(5).items()},
    }
    return out, top


def plot_scenario_uplift(data: Dict[str, pd.DataFrame], outdir: Path) -> Tuple[Path, Dict[str, Dict[str, float]]]:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), constrained_layout=True)
    uplift_out: Dict[str, Dict[str, float]] = {}

    for ax, key, title, label in [
        (axes[0], "ccp_cases", "CCP scenario objective uplift", "ccp"),
        (axes[1], "icp_cases", "ICP+Bias scenario objective uplift", "icp_bias"),
    ]:
        df = data[key].copy()
        g = df.groupby("scenario_family", as_index=False)["objective"].mean()
        base = float(g.loc[g["scenario_family"] == "nominal", "objective"].iloc[0])
        g["uplift_vs_nominal"] = g["objective"] - base

        sns.barplot(
            data=g,
            x="scenario_family",
            y="uplift_vs_nominal",
            hue="scenario_family",
            order=["nominal", "shifted_surface", "ood_nonlin"],
            palette="Set2",
            legend=False,
            ax=ax,
        )
        ax.axhline(0.0, color="#111827", lw=1.2)
        ax.set_title(title)
        ax.set_ylabel("mean objective uplift vs nominal")
        ax.grid(True, axis="y", alpha=0.25)

        uplift_out[label] = {r["scenario_family"]: float(r["uplift_vs_nominal"]) for _, r in g.iterrows()}

    out = outdir / "deep_scenario_uplift.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out, uplift_out


def _pick_design_case(cases: pd.DataFrame, design_id: str) -> str:
    sub = cases[(cases["design_id"] == design_id) & (cases["scenario_family"] == "nominal")].sort_values("scenario_id")
    return str(sub.iloc[0]["case_id"])


def _downsample(df: pd.DataFrame, n_max: int = 3000) -> pd.DataFrame:
    if len(df) <= n_max:
        return df
    idx = np.linspace(0, len(df) - 1, n_max).astype(int)
    return df.iloc[idx]


def plot_waveform_top_vs_median(data: Dict[str, pd.DataFrame], outdir: Path) -> Tuple[Path, Dict[str, str]]:
    ccp_agg = data["ccp_agg"].sort_values("robust_objective").reset_index(drop=True)
    icp_agg = data["icp_agg"].sort_values("robust_objective").reset_index(drop=True)

    ccp_best = str(ccp_agg.iloc[0]["design_id"])
    ccp_mid = str(ccp_agg.iloc[len(ccp_agg) // 2]["design_id"])
    icp_best = str(icp_agg.iloc[0]["design_id"])
    icp_mid = str(icp_agg.iloc[len(icp_agg) // 2]["design_id"])

    ccp_best_case = _pick_design_case(data["ccp_cases"], ccp_best)
    ccp_mid_case = _pick_design_case(data["ccp_cases"], ccp_mid)
    icp_best_case = _pick_design_case(data["icp_cases"], icp_best)
    icp_mid_case = _pick_design_case(data["icp_cases"], icp_mid)

    ccp_best_tr = _downsample(data["ccp_tr"][data["ccp_tr"]["case_id"] == ccp_best_case].sort_values("time"))
    ccp_mid_tr = _downsample(data["ccp_tr"][data["ccp_tr"]["case_id"] == ccp_mid_case].sort_values("time"))
    icp_best_tr = _downsample(data["icp_tr"][data["icp_tr"]["case_id"] == icp_best_case].sort_values("time"))
    icp_mid_tr = _downsample(data["icp_tr"][data["icp_tr"]["case_id"] == icp_mid_case].sort_values("time"))

    t_ccp = data["target_ccp"]
    t_bias = data["target_bias"]

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)

    axes[0, 0].plot(ccp_best_tr["time"] * 1e6, ccp_best_tr["v_port"], lw=1.8, color="#2563eb", label=f"best ({ccp_best})")
    axes[0, 0].plot(ccp_mid_tr["time"] * 1e6, ccp_mid_tr["v_port"], lw=1.4, color="#dc2626", label=f"median ({ccp_mid})")
    axes[0, 0].plot(t_ccp["time"] * 1e6, t_ccp["v_target"], lw=1.2, ls="--", color="#111827", label="target")
    axes[0, 0].set_title("CCP v_port: top vs median robust design")
    axes[0, 0].set_xlabel("time [us]")
    axes[0, 0].set_ylabel("voltage [V]")
    axes[0, 0].grid(True, alpha=0.25)
    axes[0, 0].legend(fontsize=9)

    axes[0, 1].plot(ccp_best_tr["time"] * 1e6, ccp_best_tr["i_port"], lw=1.8, color="#2563eb", label=f"best ({ccp_best})")
    axes[0, 1].plot(ccp_mid_tr["time"] * 1e6, ccp_mid_tr["i_port"], lw=1.4, color="#dc2626", label=f"median ({ccp_mid})")
    axes[0, 1].set_title("CCP i_port: stress comparison")
    axes[0, 1].set_xlabel("time [us]")
    axes[0, 1].set_ylabel("current [A]")
    axes[0, 1].grid(True, alpha=0.25)
    axes[0, 1].legend(fontsize=9)

    axes[1, 0].plot(icp_best_tr["time"] * 1e6, icp_best_tr["v_bias"], lw=1.8, color="#2563eb", label=f"best ({icp_best})")
    axes[1, 0].plot(icp_mid_tr["time"] * 1e6, icp_mid_tr["v_bias"], lw=1.4, color="#dc2626", label=f"median ({icp_mid})")
    axes[1, 0].plot(t_bias["time"] * 1e6, t_bias["v_target"], lw=1.2, ls="--", color="#111827", label="target")
    axes[1, 0].set_title("ICP+Bias v_bias: top vs median robust design")
    axes[1, 0].set_xlabel("time [us]")
    axes[1, 0].set_ylabel("voltage [V]")
    axes[1, 0].grid(True, alpha=0.25)
    axes[1, 0].legend(fontsize=9)

    axes[1, 1].plot(icp_best_tr["time"] * 1e6, icp_best_tr["i_bias"], lw=1.8, color="#2563eb", label=f"best ({icp_best})")
    axes[1, 1].plot(icp_mid_tr["time"] * 1e6, icp_mid_tr["i_bias"], lw=1.4, color="#dc2626", label=f"median ({icp_mid})")
    axes[1, 1].set_title("ICP+Bias i_bias: stress comparison")
    axes[1, 1].set_xlabel("time [us]")
    axes[1, 1].set_ylabel("current [A]")
    axes[1, 1].grid(True, alpha=0.25)
    axes[1, 1].legend(fontsize=9)

    out = outdir / "deep_waveform_top_vs_median.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)

    ids = {
        "ccp_best_design": ccp_best,
        "ccp_median_design": ccp_mid,
        "icp_best_design": icp_best,
        "icp_median_design": icp_mid,
    }
    return out, ids


def _summary_stats(data: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, float]]:
    ccp = data["ccp_agg"]
    icp = data["icp_agg"]
    out: Dict[str, Dict[str, float]] = {}

    for name, df in [("ccp", ccp), ("icp_bias", icp)]:
        q = df["robust_objective"].quantile([0.1, 0.5, 0.9]).to_dict()
        out[name] = {
            "robust_q10": float(q[0.1]),
            "robust_q50": float(q[0.5]),
            "robust_q90": float(q[0.9]),
            "robust_iqr": float(df["robust_objective"].quantile(0.75) - df["robust_objective"].quantile(0.25)),
            "best_design_robust": float(df["robust_objective"].min()),
            "worst_design_robust": float(df["robust_objective"].max()),
        }
    return out


def write_deep_summary(outdir: Path, outputs: List[Path], stats: Dict[str, object]) -> Path:
    lines = [
        "# Deep Dive Summary",
        "",
        "This summary complements INSIGHT_SUMMARY.md with distribution-level diagnostics.",
        "",
        "## Generated deep-dive figures",
    ]
    for p in outputs:
        lines.append(f"- {p.name}")

    lines.extend([
        "",
        "## Key numbers",
        json.dumps(stats, ensure_ascii=False, indent=2),
        "",
    ])

    out = outdir / "DEEP_DIVE_SUMMARY.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-root", type=Path, default=Path(__file__).resolve().parents[1] / "benchmark")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--outdir", type=Path, default=Path(__file__).resolve().parents[1] / "results" / "benchmark_figures")
    args = parser.parse_args()

    outdir = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="notebook")

    data = _load(args.benchmark_root, args.repo_root)

    outputs: List[Path] = []
    stats: Dict[str, object] = {}

    for p in plot_schemdraw_circuits(data, outdir):
        outputs.append(p)

    rf_paths, rf_stats = plot_smith_and_rf_metrics(data, outdir, z0=Z0_DEFAULT)
    outputs.extend(rf_paths)

    p = plot_baseline_ecdf(data, outdir)
    outputs.append(p)

    p = plot_baseline_split_hist(data, outdir)
    outputs.append(p)

    p, idood_table = plot_id_ood_ci(data, outdir)
    outputs.append(p)
    idood_csv = outdir / "deep_id_ood_ci_table.csv"
    idood_table.to_csv(idood_csv, index=False)
    outputs.append(idood_csv)

    p, pareto_counts = plot_pareto_frontier(data, outdir)
    outputs.append(p)

    p, split_stats = plot_robust_split_violin(data, outdir)
    outputs.append(p)

    p, topo_stats = plot_topology_effect(data, outdir)
    outputs.append(p)

    p, stability_stats = plot_stability_index(data, outdir)
    outputs.append(p)

    p, corr_top = plot_factor_correlation(data, outdir)
    outputs.append(p)

    p, uplift = plot_scenario_uplift(data, outdir)
    outputs.append(p)

    p, rank_ids = plot_waveform_top_vs_median(data, outdir)
    outputs.append(p)

    stats["id_ood_ci"] = idood_table.to_dict(orient="records")
    stats["rf_matching"] = rf_stats
    stats["pareto_frontier_counts"] = pareto_counts
    stats["split_robust_means"] = split_stats
    stats["topology_robust_means"] = topo_stats
    stats["stability_ratio"] = stability_stats
    stats["top_correlations"] = corr_top
    stats["scenario_uplift_vs_nominal"] = uplift
    stats["rank_design_ids"] = rank_ids
    stats["distribution"] = _summary_stats(data)

    json_path = outdir / "deep_dive_stats.json"
    json_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    outputs.append(json_path)

    p = write_deep_summary(outdir, outputs, stats)
    outputs.append(p)

    print(f"Wrote {len(outputs)} deep-dive outputs to {outdir}")
    for op in outputs:
        print(f" - {op}")


if __name__ == "__main__":
    main()
