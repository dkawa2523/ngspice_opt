#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
import numpy as np
import pandas as pd
import schemdraw
import schemdraw.elements as elm
import yaml


def _fmt_eng(v: float) -> str:
    if v == 0:
        return "0"
    p = int(np.floor(np.log10(abs(v)) / 3) * 3)
    p = max(min(p, 9), -12)
    scale = 10.0 ** p
    s = v / scale
    suf = {-12: "p", -9: "n", -6: "u", -3: "m", 0: "", 3: "k", 6: "M", 9: "G"}[p]
    return f"{s:.3g}{suf}"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_history(workdir: Path) -> pd.DataFrame:
    d = json.loads((workdir / "history.json").read_text(encoding="utf-8"))
    rows = []
    for i, h in enumerate(d["history"], start=1):
        row = {
            "trial": i,
            "phase": h["phase"],
            "aggregate_objective": float(h["aggregate_objective"]),
            **{k: float(v) for k, v in h["mean_metrics"].items()},
            **{f"std_{k}": float(v) for k, v in h["std_metrics"].items()},
        }
        for k, v in h["design"].items():
            row[f"design__{k}"] = v
        rows.append(row)
    return pd.DataFrame(rows)


def _draw_ccp_schematic_from_design(design: Dict[str, Any], out_png: Path) -> None:
    topo = str(design["topology"])
    d = schemdraw.Drawing(show=False)
    d.config(unit=1.9, fontsize=9)
    d += elm.SourceSin().label(f"Vsrc\\n{float(design['VAC_BIAS']):.1f}V\\n{float(design['F_BIAS'])/1e6:.3g}MHz")
    d += elm.Resistor().right().label(f"Rgen\\n{_fmt_eng(float(design['R_GEN']))}Ω")

    if topo == "PI":
        n0 = d.here
        d += elm.Line().right()
        d.push()
        d += elm.Capacitor().down().at(n0).label(f"Cin\\n{_fmt_eng(float(design['C_MATCH_IN']))}F")
        d += elm.Ground()
        d.pop()
        d += elm.Inductor().right().label(f"Lmatch\\n{_fmt_eng(float(design['L_MATCH']))}H")
        n1 = d.here
        d.push()
        d += elm.Capacitor().down().at(n1).label(f"Cout\\n{_fmt_eng(float(design['C_MATCH_OUT']))}F")
        d += elm.Ground()
        d.pop()
    else:
        d += elm.Inductor().right().label(f"Lmatch\\n{_fmt_eng(float(design['L_MATCH']))}H")
        n1 = d.here
        d.push()
        d += elm.Capacitor().down().at(n1).label(f"Cout\\n{_fmt_eng(float(design['C_MATCH_OUT']))}F")
        d += elm.Ground()
        d.pop()

    rcab = float(design["CABLE_R_PER_M"]) * float(design["CABLE_LEN_M"])
    lcab = float(design["CABLE_L_PER_M"]) * float(design["CABLE_LEN_M"])
    ccab = float(design["CABLE_C_PER_M"]) * float(design["CABLE_LEN_M"])

    d += elm.Resistor().right().label(f"Rcable\\n{_fmt_eng(rcab)}Ω")
    d += elm.Inductor().right().label(f"Lcable\\n{_fmt_eng(lcab)}H")
    n2 = d.here
    d.push()
    d += elm.Capacitor().down().at(n2).label(f"Ccable\\n{_fmt_eng(ccab)}F")
    d += elm.Ground()
    d.pop()

    d += elm.Capacitor().right().label(f"Cblock\\n{_fmt_eng(float(design['C_BLOCK']))}F")
    n3 = d.here
    d.push()
    d += elm.Resistor().down().at(n3).label("Rplasma\\n90Ω")
    d += elm.Ground()
    d.pop()
    d.push()
    d += elm.Capacitor().down().at(n3).label("Cplasma\\n35pF")
    d += elm.Ground()
    d.pop()

    out_png.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(out_png), dpi=220)


def _draw_icp_schematic_from_design(design: Dict[str, Any], out_png: Path) -> None:
    d = schemdraw.Drawing(show=False)
    d.config(unit=1.8, fontsize=9)

    d += elm.SourceSin().label(f"ICP\\n{float(design['VICP_AC']):.1f}V\\n{float(design['F_ICP'])/1e6:.3g}MHz")
    d += elm.Resistor().right().label(f"Rgen\\n{_fmt_eng(float(design['R_ICP_GEN']))}Ω")
    d += elm.Inductor().right().label(f"Lcoil\\n{_fmt_eng(float(design['L_COIL_MATCH']))}H")
    n0 = d.here
    d.push()
    d += elm.Capacitor().down().at(n0).label(f"Ccoil\\n{_fmt_eng(float(design['C_COIL_MATCH_OUT']))}F")
    d += elm.Ground()
    d.pop()
    d += elm.Resistor().right().label("Plasma coil\\n0.8Ω")
    d += elm.Ground()

    d.move(dy=-5.0)
    d += elm.SourceSin().label(
        f"Bias\\n{float(design['VBIAS_AC']):.1f}V AC\\n{float(design['VBIAS_DC']):.1f}V DC\\n{float(design['F_BIAS'])/1e6:.3g}MHz"
    )
    d += elm.Resistor().right().label(f"Rgen\\n{_fmt_eng(float(design['R_BIAS_GEN']))}Ω")
    d += elm.Inductor().right().label(f"Lbias\\n{_fmt_eng(float(design['L_BIAS_MATCH']))}H")
    n1 = d.here
    d.push()
    d += elm.Capacitor().down().at(n1).label(f"Cbias\\n{_fmt_eng(float(design['C_BIAS_MATCH_OUT']))}F")
    d += elm.Ground()
    d.pop()
    d += elm.Capacitor().right().label(f"Cblock\\n{_fmt_eng(float(design['C_BLOCK_BIAS']))}F")
    n2 = d.here
    d.push()
    d += elm.Resistor().down().at(n2).label("Rplasma\\n120Ω")
    d += elm.Ground()
    d.pop()
    d.push()
    d += elm.Capacitor().down().at(n2).label("Cplasma\\n42pF")
    d += elm.Ground()
    d.pop()

    out_png.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(out_png), dpi=220)


def _extract_design(row: pd.Series) -> Dict[str, Any]:
    out = {}
    for c, v in row.items():
        if c.startswith("design__"):
            out[c.split("design__", 1)[1]] = v
    return out


def _enrich_metrics(df: pd.DataFrame, target_selfbias: float) -> pd.DataFrame:
    x = df.copy()
    x["avg_power_abs"] = x["avg_power"].abs()
    x["selfbias_error"] = (x["selfbias"] - target_selfbias).abs()
    x["risk_term"] = x["aggregate_objective"] - x["objective"]
    x["best_so_far"] = x["aggregate_objective"].cummin()
    return x


def plot_optimizer_progress(df: pd.DataFrame, problem: str, outdir: Path) -> Path:
    fig, axes = plt.subplots(3, 1, figsize=(13, 10), constrained_layout=True)

    color = np.where(df["phase"] == "random", "#2563eb", "#dc2626")
    axes[0].scatter(df["trial"], df["aggregate_objective"], c=color, s=32, alpha=0.85)
    axes[0].plot(df["trial"], df["best_so_far"], color="#111827", lw=1.8, label="best so far")
    axes[0].set_title(f"{problem}: aggregate objective trajectory")
    axes[0].set_xlabel("trial")
    axes[0].set_ylabel("aggregate_objective")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(loc="upper right")

    axes[1].plot(df["trial"], df["objective"], label="mean objective", color="#2563eb")
    axes[1].plot(df["trial"], df["risk_term"], label="risk term", color="#dc2626")
    axes[1].set_title(f"{problem}: objective decomposition")
    axes[1].set_xlabel("trial")
    axes[1].set_ylabel("value")
    axes[1].grid(True, alpha=0.25)
    axes[1].legend(loc="upper right")

    axes[2].plot(df["trial"], df["v_rmse"], label="v_rmse", color="#1d4ed8")
    axes[2].plot(df["trial"], df["i_peak"], label="i_peak", color="#b91c1c")
    axes[2].plot(df["trial"], df["avg_power_abs"], label="|avg_power|", color="#0f766e")
    axes[2].plot(df["trial"], df["selfbias_error"], label="|selfbias-target|", color="#a16207")
    axes[2].set_title(f"{problem}: raw metric trajectory")
    axes[2].set_xlabel("trial")
    axes[2].set_ylabel("metric value")
    axes[2].grid(True, alpha=0.25)
    axes[2].legend(loc="upper right", ncol=2, fontsize=9)

    out = outdir / f"optimizer_progress_{problem}.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def _metric_specs() -> List[Tuple[str, str]]:
    return [
        ("aggregate_objective", "Aggregate Objective"),
        ("v_rmse", "Voltage RMSE"),
        ("i_peak", "Peak Current"),
        ("avg_power_abs", "Abs Avg Power"),
        ("selfbias_error", "Self-Bias Error"),
    ]


def _ratio_matrix(summary_df: pd.DataFrame) -> Tuple[np.ndarray, List[str], List[str]]:
    metrics = _metric_specs()
    keys = [m[0] for m in metrics]
    labels = [m[1] for m in metrics]
    mat = np.full((len(keys), len(keys)), np.nan, dtype=float)
    for r, opt in enumerate(keys):
        row = summary_df.loc[summary_df["optimized_metric"] == opt]
        if row.empty:
            continue
        for c, metric in enumerate(keys):
            mat[r, c] = float(row.iloc[0][f"ratio_vs_median__{metric}"])
    return mat, keys, labels


def _fmt_ratio_cell(v: float) -> str:
    if not np.isfinite(v):
        return ""
    if v >= 10.0:
        return ">10x"
    if v <= 0.2:
        return "<0.2x"
    return f"{v:.2f}x"


def plot_metric_ratio_heatmap(summary_df: pd.DataFrame, problem: str, outdir: Path) -> Path:
    mat, keys, labels = _ratio_matrix(summary_df)
    mat_show = np.clip(mat, 0.2, 10.0)
    vmin = 0.2
    vmax = 10.0
    norm = TwoSlopeNorm(vcenter=1.0, vmin=vmin, vmax=vmax)

    fig, ax = plt.subplots(figsize=(9.5, 7.0), constrained_layout=True)
    im = ax.imshow(mat_show, cmap="RdYlGn_r", norm=norm)
    ax.set_xticks(np.arange(len(labels)))
    ax.set_yticks(np.arange(len(labels)))
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_yticklabels(labels)
    ax.set_xlabel("evaluated metric")
    ax.set_ylabel("optimized metric")
    ax.set_title(f"{problem}: winner/median ratio heatmap")

    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            v = mat[i, j]
            if not np.isfinite(v):
                continue
            tv = mat_show[i, j]
            tc = "#111827" if abs(tv - 1.0) < 0.45 else "white"
            ax.text(j, i, _fmt_ratio_cell(v), ha="center", va="center", fontsize=9, color=tc)

    fig.colorbar(im, ax=ax, label="winner / median trial")
    out = outdir / f"optimizer_metric_ratio_heatmap_{problem}.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_metric_effect_summary(summary_df: pd.DataFrame, problem: str, outdir: Path) -> Path:
    metrics = _metric_specs()
    keys = [m[0] for m in metrics]
    labels = [m[1] for m in metrics]
    x = np.arange(len(keys))
    width = 0.14

    fig, ax = plt.subplots(figsize=(12, 6.5), constrained_layout=True)
    for i, opt in enumerate(keys):
        row = summary_df.loc[summary_df["optimized_metric"] == opt]
        if row.empty:
            continue
        ratios = [float(row.iloc[0][f"ratio_vs_median__{k}"]) for k in keys]
        deltas = [float(np.clip(v, 0.2, 10.0)) for v in ratios]
        ax.bar(
            x + (i - (len(keys) - 1) / 2.0) * width,
            deltas,
            width=width,
            label=labels[i],
            alpha=0.9,
        )

    ax.axhline(1.0, color="#111827", lw=1.2, ls="--")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_ylabel("winner / median trial (clipped 0.2x - 10x)")
    ax.set_ylim(0, 10.5)
    ax.set_title(f"{problem}: effect summary by optimized metric (clipped)")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(loc="best", fontsize=8, ncol=2)

    out = outdir / f"optimizer_metric_effect_summary_{problem}.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_metric_story(df: pd.DataFrame, problem: str, outdir: Path) -> Tuple[List[Path], List[Dict[str, Any]]]:
    metrics = _metric_specs()
    median_row = df.iloc[(df["aggregate_objective"] - df["aggregate_objective"].median()).abs().argsort().iloc[0]]

    outputs: List[Path] = []
    summary_rows: List[Dict[str, Any]] = []

    for metric, label in metrics:
        winner = df.loc[df[metric].idxmin()]
        design = _extract_design(winner)
        schematic_png = outdir / f"optimizer_{problem}_{metric}_schematic.png"
        if problem == "ccp":
            _draw_ccp_schematic_from_design(design, schematic_png)
        else:
            _draw_icp_schematic_from_design(design, schematic_png)

        cmp_metrics = [m[0] for m in metrics]
        winner_vals = np.array([float(winner[m]) for m in cmp_metrics], dtype=float)
        median_vals = np.array([float(median_row[m]) for m in cmp_metrics], dtype=float)
        ratio = winner_vals / np.maximum(median_vals, 1e-12)

        fig, axes = plt.subplots(1, 2, figsize=(14, 5.8), constrained_layout=True)
        img = plt.imread(schematic_png)
        axes[0].imshow(img)
        axes[0].axis("off")
        axes[0].set_title(f"{problem} circuit for best {label}")

        y = np.arange(len(cmp_metrics))
        colors = np.where(ratio <= 1.0, "#2563eb", "#dc2626")
        axes[1].barh(y, ratio, color=colors)
        axes[1].axvline(1.0, color="#111827", lw=1.1, ls="--")
        axes[1].set_yticks(y)
        axes[1].set_yticklabels([m[1] for m in metrics], fontsize=9)
        axes[1].set_xlabel("winner / median trial")
        axes[1].set_title(f"Effect summary for optimizing {label}")
        axes[1].grid(True, axis="x", alpha=0.25)

        txt = f"trial={int(winner['trial'])}, phase={winner['phase']}\n{metric}={float(winner[metric]):.4g}"
        axes[1].text(0.02, -0.18, txt, transform=axes[1].transAxes, fontsize=9)

        out_story = outdir / f"optimizer_{problem}_{metric}_story.png"
        fig.savefig(out_story, dpi=180)
        plt.close(fig)

        outputs.extend([schematic_png, out_story])

        row = {"problem": problem, "optimized_metric": metric, "trial": int(winner["trial"]), "phase": str(winner["phase"])}
        for cm in cmp_metrics:
            row[f"winner__{cm}"] = float(winner[cm])
            row[f"ratio_vs_median__{cm}"] = float(row[f"winner__{cm}"] / max(float(median_row[cm]), 1e-12))
        summary_rows.append(row)

    return outputs, summary_rows


def plot_metric_tradeoff_scatter(df: pd.DataFrame, problem: str, outdir: Path) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), constrained_layout=True)
    spec = [
        ("v_rmse", "i_peak"),
        ("v_rmse", "avg_power_abs"),
        ("v_rmse", "selfbias_error"),
        ("i_peak", "avg_power_abs"),
    ]
    for ax, (x, y) in zip(axes.flatten(), spec):
        sc = ax.scatter(df[x], df[y], c=df["aggregate_objective"], cmap="viridis_r", s=45, alpha=0.85, edgecolor="none")
        ax.set_xlabel(x)
        ax.set_ylabel(y)
        ax.grid(True, alpha=0.25)
        fig.colorbar(sc, ax=ax, label="aggregate_objective")
    fig.suptitle(f"{problem}: trade-off scatter by objective components")
    out = outdir / f"optimizer_tradeoff_{problem}.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_cross_problem_ratio_heatmap(
    ccp_summary_df: pd.DataFrame,
    icp_summary_df: pd.DataFrame,
    outdir: Path,
) -> Path:
    ccp_mat, _, labels = _ratio_matrix(ccp_summary_df)
    icp_mat, _, _ = _ratio_matrix(icp_summary_df)
    ccp_show = np.clip(ccp_mat, 0.2, 10.0)
    icp_show = np.clip(icp_mat, 0.2, 10.0)
    vmin = 0.2
    vmax = 10.0
    norm = TwoSlopeNorm(vcenter=1.0, vmin=vmin, vmax=vmax)

    fig, axes = plt.subplots(1, 2, figsize=(14.5, 6.5), constrained_layout=True)
    for ax, mat, title in [
        (axes[0], ccp_mat, "CCP"),
        (axes[1], icp_mat, "ICP+Bias"),
    ]:
        mshow = ccp_show if title == "CCP" else icp_show
        im = ax.imshow(mshow, cmap="RdYlGn_r", norm=norm)
        ax.set_xticks(np.arange(len(labels)))
        ax.set_yticks(np.arange(len(labels)))
        ax.set_xticklabels(labels, rotation=30, ha="right")
        ax.set_yticklabels(labels)
        ax.set_xlabel("evaluated metric")
        ax.set_ylabel("optimized metric")
        ax.set_title(title)
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                if np.isfinite(mat[i, j]):
                    tv = mshow[i, j]
                    tc = "#111827" if abs(tv - 1.0) < 0.45 else "white"
                    ax.text(j, i, _fmt_ratio_cell(mat[i, j]), ha="center", va="center", fontsize=8, color=tc)

    fig.colorbar(im, ax=axes.ravel().tolist(), label="winner / median trial")
    fig.suptitle("Optimizer metric effect comparison (CCP vs ICP+Bias)")
    out = outdir / "optimizer_metric_ratio_heatmap_compare.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def run_for_problem(problem: str, config_path: Path, workdir: Path, outdir: Path) -> Tuple[List[Path], pd.DataFrame]:
    cfg = _load_yaml(config_path)
    target_selfbias = float(cfg["objective"]["target_selfbias"])
    df = _enrich_metrics(_load_history(workdir), target_selfbias=target_selfbias)

    out_sub = outdir / problem
    out_sub.mkdir(parents=True, exist_ok=True)

    outputs: List[Path] = []
    outputs.append(plot_optimizer_progress(df, problem, out_sub))
    outputs.append(plot_metric_tradeoff_scatter(df, problem, out_sub))
    story_outputs, summary_rows = plot_metric_story(df, problem, out_sub)
    outputs.extend(story_outputs)

    summary_df = pd.DataFrame(summary_rows)
    summary_csv = out_sub / f"optimizer_metric_winners_{problem}.csv"
    summary_df.to_csv(summary_csv, index=False)
    outputs.append(summary_csv)
    outputs.append(plot_metric_ratio_heatmap(summary_df, problem, out_sub))
    outputs.append(plot_metric_effect_summary(summary_df, problem, out_sub))

    # Save trial table for custom user analysis.
    trial_csv = out_sub / f"optimizer_trials_{problem}.csv"
    df.to_csv(trial_csv, index=False)
    outputs.append(trial_csv)

    return outputs, summary_df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--ccp-config", type=Path, default=Path("configs/design_space_ccp.yaml"))
    parser.add_argument("--icp-config", type=Path, default=Path("configs/design_space_icp_bias.yaml"))
    parser.add_argument("--ccp-workdir", type=Path, default=Path("results/ccp_run"))
    parser.add_argument("--icp-workdir", type=Path, default=Path("results/icp_bias_run"))
    parser.add_argument("--outdir", type=Path, default=Path("results/optimizer_story"))
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    outdir = (repo_root / args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    outputs: List[Path] = []
    ccp_outputs, ccp_summary = run_for_problem(
        "ccp",
        config_path=repo_root / args.ccp_config,
        workdir=repo_root / args.ccp_workdir,
        outdir=outdir,
    )
    outputs.extend(ccp_outputs)
    icp_outputs, icp_summary = run_for_problem(
        "icp_bias",
        config_path=repo_root / args.icp_config,
        workdir=repo_root / args.icp_workdir,
        outdir=outdir,
    )
    outputs.extend(icp_outputs)
    outputs.append(plot_cross_problem_ratio_heatmap(ccp_summary, icp_summary, outdir))

    print(f"Wrote {len(outputs)} optimizer story outputs to {outdir}")
    for p in outputs:
        print(f" - {p}")


if __name__ == "__main__":
    main()
