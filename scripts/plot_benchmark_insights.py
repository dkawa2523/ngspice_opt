#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.patches import FancyBboxPatch


SPLIT_ORDER = ["train", "val", "test_id", "test_ood"]
SCENARIO_ORDER = ["nominal", "shifted_surface", "ood_nonlin"]


def _load_bundle(benchmark_root: Path) -> Dict[str, pd.DataFrame]:
    return {
        "ccp_cases": pd.read_csv(benchmark_root / "ccp_codesign" / "ccp_cases.csv"),
        "ccp_agg": pd.read_csv(benchmark_root / "ccp_codesign" / "ccp_design_aggregates.csv"),
        "ccp_traces": pd.read_csv(benchmark_root / "ccp_codesign" / "ccp_traces.csv.gz"),
        "icp_cases": pd.read_csv(benchmark_root / "icp_bias_codesign" / "icp_bias_cases.csv"),
        "icp_agg": pd.read_csv(benchmark_root / "icp_bias_codesign" / "icp_bias_design_aggregates.csv"),
        "icp_traces": pd.read_csv(benchmark_root / "icp_bias_codesign" / "icp_bias_traces.csv.gz"),
        "ccp_base": pd.read_csv(benchmark_root / "baselines" / "ccp_identification_baseline.csv"),
        "icp_base": pd.read_csv(benchmark_root / "baselines" / "icp_identification_baseline.csv"),
    }


def _downsample(df: pd.DataFrame, n_max: int) -> pd.DataFrame:
    if len(df) <= n_max:
        return df
    idx = np.linspace(0, len(df) - 1, n_max).astype(int)
    return df.iloc[idx].copy()


def _pick_case(cases: pd.DataFrame, design_id: str) -> str:
    sub = cases[cases["design_id"] == design_id].copy()
    if "scenario_family" in sub.columns:
        nominal = sub[sub["scenario_family"] == "nominal"]
        if len(nominal) > 0:
            sub = nominal
    if "scenario_id" in sub.columns:
        sub = sub.sort_values("scenario_id")
    return str(sub.iloc[0]["case_id"])


def _add_box(ax, xy: Tuple[float, float], w: float, h: float, text: str, fc: str) -> None:
    box = FancyBboxPatch(xy, w, h, boxstyle="round,pad=0.02,rounding_size=0.03", fc=fc, ec="#374151", lw=1.2)
    ax.add_patch(box)
    ax.text(xy[0] + w / 2.0, xy[1] + h / 2.0, text, ha="center", va="center", fontsize=10)


def _draw_ccp_circuit(ax: plt.Axes, best: pd.Series) -> None:
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4)
    ax.axis("off")

    _add_box(ax, (0.5, 2.5), 1.5, 0.9, "RF Source", "#dbeafe")
    _add_box(ax, (2.5, 2.5), 2.0, 0.9, "Matching\n(L / PI)", "#dcfce7")
    _add_box(ax, (5.0, 2.5), 1.8, 0.9, "Cable", "#fef3c7")
    _add_box(ax, (7.2, 2.3), 2.1, 1.2, "Plasma CCP\nROM", "#fee2e2")

    ax.plot([2.0, 2.5], [2.95, 2.95], color="#374151", lw=2)
    ax.plot([4.5, 5.0], [2.95, 2.95], color="#374151", lw=2)
    ax.plot([6.8, 7.2], [2.95, 2.95], color="#374151", lw=2)

    ax.plot([9.3, 9.7, 9.7, 0.8], [2.9, 2.9, 1.0, 1.0], color="#6b7280", lw=1.6)
    ax.plot([0.8, 0.8], [1.0, 2.5], color="#6b7280", lw=1.6)
    ax.text(9.05, 1.15, "Return path", fontsize=9, color="#374151")

    txt = (
        f"best design_id: {best['design_id']}\n"
        f"topology={best['topology']}, VAC={best['VAC_BIAS']:.1f} V\n"
        f"L_MATCH={best['L_MATCH']:.2e} H, C_BLOCK={best['C_BLOCK']:.2e} F\n"
        f"robust={best['robust_objective']:.4f}"
    )
    ax.text(0.3, 0.1, txt, fontsize=9, va="bottom", ha="left", bbox=dict(fc="white", ec="#d1d5db", boxstyle="round,pad=0.3"))


def _draw_icp_circuit(ax: plt.Axes, best: pd.Series) -> None:
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 6)
    ax.axis("off")

    _add_box(ax, (0.5, 4.2), 1.8, 0.9, "ICP Source", "#dbeafe")
    _add_box(ax, (2.8, 4.2), 2.2, 0.9, "Coil Match", "#dcfce7")
    _add_box(ax, (5.5, 4.2), 2.0, 0.9, "Coil Feed", "#fef3c7")

    _add_box(ax, (0.5, 1.7), 1.8, 0.9, "Bias Source", "#dbeafe")
    _add_box(ax, (2.8, 1.7), 2.2, 0.9, "Bias Match", "#dcfce7")
    _add_box(ax, (5.5, 1.7), 2.0, 0.9, "Bias Feed", "#fef3c7")

    _add_box(ax, (8.3, 2.5), 3.0, 1.8, "Plasma ICP+Bias\nShared-State ROM", "#fee2e2")

    ax.plot([2.3, 2.8], [4.65, 4.65], color="#374151", lw=2)
    ax.plot([5.0, 5.5], [4.65, 4.65], color="#374151", lw=2)
    ax.plot([7.5, 8.3], [4.65, 3.8], color="#374151", lw=2)

    ax.plot([2.3, 2.8], [2.15, 2.15], color="#374151", lw=2)
    ax.plot([5.0, 5.5], [2.15, 2.15], color="#374151", lw=2)
    ax.plot([7.5, 8.3], [2.15, 3.0], color="#374151", lw=2)

    ax.plot([11.3, 11.7, 11.7, 0.9], [3.4, 3.4, 0.8, 0.8], color="#6b7280", lw=1.6)
    ax.plot([0.9, 0.9], [0.8, 1.7], color="#6b7280", lw=1.6)
    ax.plot([0.9, 0.9], [0.8, 4.2], color="#6b7280", lw=1.6)
    ax.text(10.8, 1.0, "Common return / ground", fontsize=9, color="#374151")

    txt = (
        f"best design_id: {best['design_id']}\n"
        f"coil={best['coil_topology']}, bias={best['bias_topology']}\n"
        f"VICP={best['VICP_AC']:.1f} V, VBIAS={best['VBIAS_AC']:.1f} V, VDC={best['VBIAS_DC']:.1f} V\n"
        f"robust={best['robust_objective']:.4f}"
    )
    ax.text(0.3, 0.1, txt, fontsize=9, va="bottom", ha="left", bbox=dict(fc="white", ec="#d1d5db", boxstyle="round,pad=0.3"))


def plot_ccp_circuit_and_waveform(bundle: Dict[str, pd.DataFrame], outdir: Path, max_trace_points: int) -> Path:
    ccp_agg = bundle["ccp_agg"]
    ccp_cases = bundle["ccp_cases"]
    ccp_traces = bundle["ccp_traces"]

    best = ccp_agg.sort_values("robust_objective").iloc[0]
    case_id = _pick_case(ccp_cases, str(best["design_id"]))
    trace = _downsample(ccp_traces[ccp_traces["case_id"] == case_id].sort_values("time"), max_trace_points)
    t_us = trace["time"].to_numpy() * 1e6

    fig, axes = plt.subplots(2, 1, figsize=(12, 9), constrained_layout=True)
    _draw_ccp_circuit(axes[0], best)

    ax_v = axes[1]
    ax_i = ax_v.twinx()
    l1, = ax_v.plot(t_us, trace["v_port"], color="#2563eb", lw=1.6, label="v_port")
    l2, = ax_v.plot(t_us, trace["v_src"], color="#60a5fa", lw=1.2, ls="--", label="v_src")
    l3, = ax_i.plot(t_us, trace["i_port"], color="#dc2626", lw=1.4, label="i_port")

    ax_v.set_title(f"CCP representative waveform (case={case_id})")
    ax_v.set_xlabel("time [us]")
    ax_v.set_ylabel("voltage [V]")
    ax_i.set_ylabel("current [A]")
    ax_v.grid(True, alpha=0.25)
    ax_v.legend([l1, l2, l3], ["v_port", "v_src", "i_port"], loc="upper right")

    out = outdir / "ccp_circuit_and_waveform.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_icp_circuit_and_waveform(bundle: Dict[str, pd.DataFrame], outdir: Path, max_trace_points: int) -> Path:
    icp_agg = bundle["icp_agg"]
    icp_cases = bundle["icp_cases"]
    icp_traces = bundle["icp_traces"]

    best = icp_agg.sort_values("robust_objective").iloc[0]
    case_id = _pick_case(icp_cases, str(best["design_id"]))
    trace = _downsample(icp_traces[icp_traces["case_id"] == case_id].sort_values("time"), max_trace_points)
    t_us = trace["time"].to_numpy() * 1e6

    fig = plt.figure(figsize=(12, 12), constrained_layout=True)
    gs = fig.add_gridspec(3, 1, height_ratios=[1.1, 1.0, 1.0])

    ax0 = fig.add_subplot(gs[0])
    ax1 = fig.add_subplot(gs[1])
    ax2 = fig.add_subplot(gs[2])

    _draw_icp_circuit(ax0, best)

    ax1i = ax1.twinx()
    a1, = ax1.plot(t_us, trace["v_coil"], color="#2563eb", lw=1.6, label="v_coil")
    a2, = ax1.plot(t_us, trace["v_src_coil"], color="#60a5fa", lw=1.2, ls="--", label="v_src_coil")
    a3, = ax1i.plot(t_us, trace["i_coil"], color="#dc2626", lw=1.4, label="i_coil")
    ax1.set_title(f"ICP coil representative waveform (case={case_id})")
    ax1.set_xlabel("time [us]")
    ax1.set_ylabel("voltage [V]")
    ax1i.set_ylabel("current [A]")
    ax1.grid(True, alpha=0.25)
    ax1.legend([a1, a2, a3], ["v_coil", "v_src_coil", "i_coil"], loc="upper right")

    ax2i = ax2.twinx()
    b1, = ax2.plot(t_us, trace["v_bias"], color="#1d4ed8", lw=1.6, label="v_bias")
    b2, = ax2i.plot(t_us, trace["i_bias"], color="#b91c1c", lw=1.4, label="i_bias")
    ax2.set_title("Bias representative waveform")
    ax2.set_xlabel("time [us]")
    ax2.set_ylabel("voltage [V]")
    ax2i.set_ylabel("current [A]")
    ax2.grid(True, alpha=0.25)
    ax2.legend([b1, b2], ["v_bias", "i_bias"], loc="upper right")

    out = outdir / "icp_bias_circuit_and_waveform.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_robust_tradeoff(bundle: Dict[str, pd.DataFrame], outdir: Path, risk_weight: float) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), constrained_layout=True)

    marker_map = {"train": "o", "val": "s", "test_id": "^", "test_ood": "D"}

    for ax, key, title in [
        (axes[0], "ccp_agg", "CCP design aggregates"),
        (axes[1], "icp_agg", "ICP+Bias design aggregates"),
    ]:
        df = bundle[key].copy()
        vmin = float(df["robust_objective"].min())
        vmax = float(df["robust_objective"].max())
        norm = plt.Normalize(vmin, vmax)

        for split in SPLIT_ORDER:
            sub = df[df["design_split"] == split]
            if len(sub) == 0:
                continue
            sc = ax.scatter(
                sub["mean_objective"],
                sub["std_objective"],
                c=sub["robust_objective"],
                cmap="viridis",
                norm=norm,
                marker=marker_map.get(split, "o"),
                s=46,
                alpha=0.86,
                label=split,
                edgecolor="none",
            )

        x_min, x_max = np.percentile(df["mean_objective"], [2, 98])
        x_line = np.linspace(x_min, x_max, 120)
        for q in [0.2, 0.5, 0.8]:
            robust_level = float(df["robust_objective"].quantile(q))
            y_line = (robust_level - x_line) / max(risk_weight, 1e-12)
            ax.plot(x_line, y_line, color="#6b7280", lw=1.0, ls="--", alpha=0.65)

        ax.set_title(f"{title}\nrobust = mean + {risk_weight:.2f} * std")
        ax.set_xlabel("mean objective")
        ax.set_ylabel("std objective")
        ax.grid(True, alpha=0.25)
        ax.legend(title="design_split", loc="upper right")
        cbar = fig.colorbar(sc, ax=ax)
        cbar.set_label("robust objective")

    out = outdir / "robust_tradeoff_scatter.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_top_design_decomposition(bundle: Dict[str, pd.DataFrame], outdir: Path, risk_weight: float, top_k: int = 12) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)

    for ax, key, title in [
        (axes[0], "ccp_agg", "CCP top robust designs"),
        (axes[1], "icp_agg", "ICP+Bias top robust designs"),
    ]:
        df = bundle[key].sort_values("robust_objective").head(top_k).copy()
        df = df.iloc[::-1]
        y = np.arange(len(df))

        mean_part = df["mean_objective"].to_numpy()
        risk_part = (risk_weight * df["std_objective"]).to_numpy()

        ax.barh(y, mean_part, color="#93c5fd", label="mean objective")
        ax.barh(y, risk_part, left=mean_part, color="#fca5a5", label=f"{risk_weight:.2f} * std")

        labels = [f"{d}\n({s})" for d, s in zip(df["design_id"], df["design_split"])]
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=8)
        ax.set_xlabel("robust objective")
        ax.set_title(title)
        ax.grid(True, axis="x", alpha=0.25)
        ax.legend(loc="lower right")

    out = outdir / "top_design_decomposition.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_case_pareto(bundle: Dict[str, pd.DataFrame], outdir: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), constrained_layout=True)

    for ax, key, title in [
        (axes[0], "ccp_cases", "CCP case-level pareto"),
        (axes[1], "icp_cases", "ICP+Bias case-level pareto"),
    ]:
        df = bundle[key].copy()
        marker_map = {"nominal": "o", "shifted_surface": "s", "ood_nonlin": "D"}
        for fam in SCENARIO_ORDER:
            sub = df[df["scenario_family"] == fam]
            if len(sub) == 0:
                continue
            sc = ax.scatter(
                sub["v_rmse"],
                sub["i_peak"],
                c=sub["objective"],
                cmap="magma_r",
                s=38,
                marker=marker_map[fam],
                alpha=0.82,
                edgecolor="none",
                label=fam,
            )
        cbar = fig.colorbar(sc, ax=ax)
        cbar.set_label("objective")
        ax.set_title(title)
        ax.set_xlabel("v_rmse")
        ax.set_ylabel("i_peak")
        ax.grid(True, alpha=0.25)
        ax.legend(title="scenario_family", loc="upper right")

    out = outdir / "case_pareto_vrmse_ipeak.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_scenario_objective_distribution(bundle: Dict[str, pd.DataFrame], outdir: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), constrained_layout=True)

    for ax, key, title in [
        (axes[0], "ccp_cases", "CCP objective distribution by scenario"),
        (axes[1], "icp_cases", "ICP+Bias objective distribution by scenario"),
    ]:
        df = bundle[key].copy()
        sns.boxplot(
            data=df,
            x="scenario_family",
            y="objective",
            hue="design_split",
            order=SCENARIO_ORDER,
            hue_order=[s for s in SPLIT_ORDER if s in set(df["design_split"])],
            ax=ax,
            fliersize=1.5,
        )
        ax.set_title(title)
        ax.set_xlabel("scenario_family")
        ax.set_ylabel("objective")
        ax.grid(True, axis="y", alpha=0.25)
        ax.legend(title="design_split", loc="upper left")

    out = outdir / "scenario_objective_distribution.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_baseline_comparison(bundle: Dict[str, pd.DataFrame], outdir: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), constrained_layout=True)

    ccp = bundle["ccp_base"].copy()
    ccp_m = ccp.melt(
        id_vars=["case_id", "split"],
        value_vars=["nrmse_meas", "nrmse_clean"],
        var_name="metric",
        value_name="value",
    )
    sns.boxplot(
        data=ccp_m,
        x="split",
        y="value",
        hue="metric",
        order=[s for s in SPLIT_ORDER if s in set(ccp_m["split"])],
        ax=axes[0],
        fliersize=1.4,
    )
    axes[0].set_title("CCP identification baseline")
    axes[0].set_xlabel("split")
    axes[0].set_ylabel("NRMSE")
    axes[0].grid(True, axis="y", alpha=0.25)
    axes[0].legend(loc="upper left")

    icp = bundle["icp_base"].copy()
    icp_m = icp.melt(
        id_vars=["case_id", "split"],
        value_vars=["coil_nrmse_meas", "bias_nrmse_meas"],
        var_name="metric",
        value_name="value",
    )
    sns.boxplot(
        data=icp_m,
        x="split",
        y="value",
        hue="metric",
        order=[s for s in SPLIT_ORDER if s in set(icp_m["split"])],
        ax=axes[1],
        fliersize=1.4,
    )
    axes[1].set_title("ICP+Bias identification baseline")
    axes[1].set_xlabel("split")
    axes[1].set_ylabel("NRMSE")
    axes[1].grid(True, axis="y", alpha=0.25)
    axes[1].legend(loc="upper left")

    out = outdir / "identification_baseline_comparison.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def _id_ood_group(split: str) -> str:
    return "ood" if split == "test_ood" else "id"


def plot_id_ood_gap(bundle: Dict[str, pd.DataFrame], outdir: Path) -> Path:
    ccp = bundle["ccp_base"].copy()
    ccp["group"] = ccp["split"].map(_id_ood_group)
    ccp_rows = []
    for metric in ["nrmse_meas", "nrmse_clean"]:
        g = ccp.groupby("group", as_index=False)[metric].mean()
        for _, row in g.iterrows():
            ccp_rows.append({"problem": "CCP", "metric": metric, "group": row["group"], "value": row[metric]})

    icp = bundle["icp_base"].copy()
    icp["group"] = icp["split"].map(_id_ood_group)
    icp_rows = []
    for metric in ["coil_nrmse_meas", "bias_nrmse_meas"]:
        g = icp.groupby("group", as_index=False)[metric].mean()
        for _, row in g.iterrows():
            icp_rows.append({"problem": "ICP+Bias", "metric": metric, "group": row["group"], "value": row[metric]})

    df = pd.DataFrame(ccp_rows + icp_rows)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2), constrained_layout=True)
    for ax, problem in zip(axes, ["CCP", "ICP+Bias"]):
        sub = df[df["problem"] == problem]
        sns.barplot(data=sub, x="metric", y="value", hue="group", hue_order=["id", "ood"], ax=ax)
        ax.set_title(f"{problem}: ID vs OOD mean error")
        ax.set_xlabel("metric")
        ax.set_ylabel("mean NRMSE")
        ax.grid(True, axis="y", alpha=0.25)
        ax.legend(loc="upper left")

    out = outdir / "id_vs_ood_gap.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def write_summary(bundle: Dict[str, pd.DataFrame], outdir: Path, outputs: List[Path], risk_weight: float) -> Path:
    ccp_best = bundle["ccp_agg"].sort_values("robust_objective").iloc[0]
    icp_best = bundle["icp_agg"].sort_values("robust_objective").iloc[0]

    ccp_base = bundle["ccp_base"].copy()
    ccp_id = float(ccp_base[ccp_base["split"] != "test_ood"]["nrmse_meas"].mean())
    ccp_ood = float(ccp_base[ccp_base["split"] == "test_ood"]["nrmse_meas"].mean())

    icp_base = bundle["icp_base"].copy()
    icp_id = float(icp_base[icp_base["split"] != "test_ood"]["bias_nrmse_meas"].mean())
    icp_ood = float(icp_base[icp_base["split"] == "test_ood"]["bias_nrmse_meas"].mean())

    ccp_scen = bundle["ccp_cases"].groupby("scenario_family", as_index=False)["objective"].mean().sort_values("objective")
    icp_scen = bundle["icp_cases"].groupby("scenario_family", as_index=False)["objective"].mean().sort_values("objective")

    lines = [
        "# Benchmark Insight Summary",
        "",
        "## Optimization objective",
        f"- robust objective = mean objective + {risk_weight:.2f} * std objective",
        f"- CCP best design: {ccp_best['design_id']} (robust={ccp_best['robust_objective']:.4f}, mean={ccp_best['mean_objective']:.4f}, std={ccp_best['std_objective']:.4f})",
        f"- ICP+Bias best design: {icp_best['design_id']} (robust={icp_best['robust_objective']:.4f}, mean={icp_best['mean_objective']:.4f}, std={icp_best['std_objective']:.4f})",
        "",
        "## Identification generalization (NRMSE)",
        f"- CCP meas error: ID={ccp_id:.4f}, OOD={ccp_ood:.4f}, OOD/ID={ccp_ood / max(ccp_id, 1e-12):.2f}x",
        f"- ICP+Bias bias-port meas error: ID={icp_id:.4f}, OOD={icp_ood:.4f}, OOD/ID={icp_ood / max(icp_id, 1e-12):.2f}x",
        "",
        "## Scenario sensitivity",
        f"- CCP (low objective -> high objective): {', '.join(ccp_scen['scenario_family'].tolist())}",
        f"- ICP+Bias (low objective -> high objective): {', '.join(icp_scen['scenario_family'].tolist())}",
        "",
        "## Generated figures",
    ]
    for p in outputs:
        lines.append(f"- {p.name}")

    out = outdir / "INSIGHT_SUMMARY.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-root", type=Path, default=Path(__file__).resolve().parents[1] / "benchmark")
    parser.add_argument("--outdir", type=Path, default=Path(__file__).resolve().parents[1] / "results" / "benchmark_figures")
    parser.add_argument("--max-trace-points", type=int, default=2500)
    parser.add_argument("--risk-weight", type=float, default=0.35)
    args = parser.parse_args()

    outdir = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    sns.set_theme(style="whitegrid", context="notebook")
    bundle = _load_bundle(args.benchmark_root)

    outputs = []
    outputs.append(plot_ccp_circuit_and_waveform(bundle, outdir, args.max_trace_points))
    outputs.append(plot_icp_circuit_and_waveform(bundle, outdir, args.max_trace_points))
    outputs.append(plot_robust_tradeoff(bundle, outdir, args.risk_weight))
    outputs.append(plot_top_design_decomposition(bundle, outdir, args.risk_weight))
    outputs.append(plot_case_pareto(bundle, outdir))
    outputs.append(plot_scenario_objective_distribution(bundle, outdir))
    outputs.append(plot_baseline_comparison(bundle, outdir))
    outputs.append(plot_id_ood_gap(bundle, outdir))
    outputs.append(write_summary(bundle, outdir, outputs, args.risk_weight))

    print(f"Wrote {len(outputs)} outputs to {outdir}")
    for p in outputs:
        print(f" - {p}")


if __name__ == "__main__":
    main()
