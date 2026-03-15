#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from common import (
    TrialResult,
    derive_lumped_parasitics,
    evaluate_ccp_objective,
    evaluate_icp_bias_objective,
    load_target_waveform,
    load_yaml,
    make_match_block_ccp,
    make_match_block_icp,
    perturb_around,
    read_wrdata_real,
    replace_tokens,
    run_ngspice,
    sample_space,
    save_json,
    summarize_metric_dicts,
)

import random


def _resolve_repo_path(repo_root: Path, path_like: Any) -> Path:
    p = Path(str(path_like))
    return p if p.is_absolute() else repo_root / p


def _validate_runtime_requirements(repo_root: Path, cfg: dict, ngspice_bin: str) -> None:
    missing_files: List[Tuple[str, Path]] = []
    for key in ("template", "portable_template", "model_include", "target_waveform"):
        path = _resolve_repo_path(repo_root, cfg.get(key, ""))
        if not path.exists():
            missing_files.append((key, path))

    if missing_files:
        lines = ["Missing required files in configuration:"]
        for key, path in missing_files:
            lines.append(f"  - {key}: {path}")
        raise FileNotFoundError("\n".join(lines))

    # Resolve ngspice either from PATH (command name) or explicit path.
    ngspice_cmd = str(ngspice_bin).strip()
    if not ngspice_cmd:
        raise ValueError("ngspice command is empty. Set --ngspice to a valid command or executable path.")
    if "/" in ngspice_cmd:
        ngspice_path = Path(ngspice_cmd)
        if not ngspice_path.exists():
            raise FileNotFoundError(f"ngspice executable not found: {ngspice_path}")
    else:
        resolved = shutil.which(ngspice_cmd)
        if resolved is None:
            raise FileNotFoundError(
                f"ngspice executable '{ngspice_cmd}' was not found in PATH. "
                "Install ngspice or pass --ngspice /path/to/ngspice."
            )


def build_render_mapping(problem: str, cfg: dict, design: Dict[str, Any], uncertainty: Dict[str, Any], output_csv: Path) -> Dict[str, Any]:
    merged = dict(design)
    merged.update(uncertainty)
    merged["MODEL_INCLUDE"] = cfg["model_include"]
    merged["OUTPUT_CSV"] = str(output_csv)

    if problem == "ccp":
        cable = derive_lumped_parasitics(
            {
                "CABLE_LEN_M": design["CABLE_LEN_M"],
                "CABLE_R_PER_M": design["CABLE_R_PER_M"],
                "CABLE_L_PER_M": design["CABLE_L_PER_M"],
                "CABLE_C_PER_M": design["CABLE_C_PER_M"],
            },
            prefix="CABLE",
        )
        ret = {
            "R_RETURN": design["RETURN_R_PER_M"] * design["RETURN_LEN_M"],
            "L_RETURN": design["RETURN_L_PER_M"] * design["RETURN_LEN_M"],
        }
        merged.update(cable)
        merged.update(ret)
        merged["MATCH_BLOCK"] = make_match_block_ccp(str(design["topology"]))
    elif problem == "icp_bias":
        coil_feed = {
            "R_COIL_FEED": design["FEED_R_PER_M"] * design["COIL_FEED_LEN_M"],
            "L_COIL_FEED": design["FEED_L_PER_M"] * design["COIL_FEED_LEN_M"],
            "C_COIL_FEED": design["FEED_C_PER_M"] * design["COIL_FEED_LEN_M"],
        }
        bias_feed = {
            "R_BIAS_FEED": design["FEED_R_PER_M"] * design["BIAS_FEED_LEN_M"],
            "L_BIAS_FEED": design["FEED_L_PER_M"] * design["BIAS_FEED_LEN_M"],
            "C_BIAS_FEED": design["FEED_C_PER_M"] * design["BIAS_FEED_LEN_M"],
        }
        merged.update(coil_feed)
        merged.update(bias_feed)
        merged["COIL_MATCH_BLOCK"] = make_match_block_icp(str(design["coil_topology"]), "coil")
        merged["BIAS_MATCH_BLOCK"] = make_match_block_icp(str(design["bias_topology"]), "bias")
    else:
        raise ValueError(problem)

    return merged


def evaluate_design(
    problem: str,
    cfg: dict,
    template_text: str,
    target_time: np.ndarray,
    target_v: np.ndarray,
    design: Dict[str, Any],
    workdir: Path,
    ngspice_bin: str,
    rng: random.Random,
) -> TrialResult:
    n_unc = int(cfg["search"]["n_uncertainty"])
    metrics_all: List[Dict[str, float]] = []
    deck_paths: List[str] = []
    waveform_paths: List[str] = []

    for k in range(n_unc):
        uncertainty = sample_space(cfg["uncertainty"], rng)

        trial_dir = workdir / f"trial_{abs(hash((str(design), k))) % (10**10)}"
        trial_dir.mkdir(parents=True, exist_ok=True)

        output_csv = trial_dir / cfg["render"]["output_csv_name"]
        deck_path = trial_dir / ("deck.cir")
        log_path = trial_dir / ("ngspice.log")

        mapping = build_render_mapping(problem, cfg, design, uncertainty, output_csv)
        deck_text = replace_tokens(template_text, mapping)
        deck_path.write_text(deck_text, encoding="utf-8")

        run_ngspice(deck_path, log_path, ngspice_bin=ngspice_bin)
        _, sim_data = read_wrdata_real(output_csv)

        if problem == "ccp":
            metrics = evaluate_ccp_objective(sim_data, target_time, target_v, cfg["objective"])
        elif problem == "icp_bias":
            metrics = evaluate_icp_bias_objective(sim_data, target_time, target_v, cfg["objective"])
        else:
            raise ValueError(problem)

        metrics_all.append(metrics)
        deck_paths.append(str(deck_path))
        waveform_paths.append(str(output_csv))

    mean_metrics, std_metrics = summarize_metric_dicts(metrics_all)
    risk = float(cfg["search"]["risk_aversion_std"]) * std_metrics["objective"]
    aggregate = mean_metrics["objective"] + risk

    return TrialResult(
        design=design,
        aggregate_objective=aggregate,
        mean_metrics=mean_metrics,
        std_metrics=std_metrics,
        deck_paths=deck_paths,
        waveform_paths=waveform_paths,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--ngspice", type=str, default="ngspice")
    parser.add_argument("--keep-all-trials", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    cfg = load_yaml(repo_root / args.config)
    _validate_runtime_requirements(repo_root, cfg, args.ngspice)
    problem = cfg["problem"]
    rng = random.Random(int(cfg["seed"]))

    target_time, target_v = load_target_waveform(repo_root / cfg["target_waveform"])
    template_text = (repo_root / cfg["template"]).read_text(encoding="utf-8")

    workdir = args.workdir
    workdir.mkdir(parents=True, exist_ok=True)

    best: TrialResult | None = None
    history: List[dict] = []

    n_random = int(cfg["search"]["n_random"])
    n_local = int(cfg["search"]["n_local"])
    local_sigma = float(cfg["search"]["local_sigma_fraction"])

    for phase, n_trials in [("random", n_random), ("local", n_local)]:
        for _ in range(n_trials):
            if phase == "random" or best is None:
                design = sample_space(cfg["design_space"], rng)
            else:
                design = perturb_around(best.design, cfg["design_space"], rng, local_sigma)

            result = evaluate_design(
                problem=problem,
                cfg=cfg,
                template_text=template_text,
                target_time=target_time,
                target_v=target_v,
                design=design,
                workdir=workdir,
                ngspice_bin=args.ngspice,
                rng=rng,
            )

            history.append(
                {
                    "phase": phase,
                    "aggregate_objective": result.aggregate_objective,
                    "design": result.design,
                    "mean_metrics": result.mean_metrics,
                    "std_metrics": result.std_metrics,
                }
            )

            if best is None or result.aggregate_objective < best.aggregate_objective:
                best = result
                print(f"[BEST] phase={phase} obj={best.aggregate_objective:.6g}")
            else:
                print(f"[TRIAL] phase={phase} obj={result.aggregate_objective:.6g}")

            if not args.keep_all_trials:
                # Keep only best trial artifacts to avoid large directories.
                # Remove decks of clearly non-best trials.
                if best is not None and result is not best:
                    for p in result.deck_paths + result.waveform_paths:
                        pp = Path(p)
                        if pp.exists():
                            try:
                                pp.unlink()
                            except OSError:
                                pass
                    parent = Path(result.deck_paths[0]).parent
                    if parent.exists():
                        try:
                            shutil.rmtree(parent)
                        except OSError:
                            pass

    assert best is not None

    save_json({"history": history}, workdir / "history.json")
    save_json(
        {
            "problem": problem,
            "best_design": best.design,
            "aggregate_objective": best.aggregate_objective,
            "mean_metrics": best.mean_metrics,
            "std_metrics": best.std_metrics,
            "deck_paths": best.deck_paths,
            "waveform_paths": best.waveform_paths,
        },
        workdir / "best_result.json",
    )

    # Also emit a portable netlist with the best design
    portable_template_text = (repo_root / cfg["portable_template"]).read_text(encoding="utf-8")
    render_best = build_render_mapping(problem, cfg, best.design, {}, workdir / "portable_dummy.csv")
    portable_text = replace_tokens(portable_template_text, render_best)
    (workdir / "best_portable.cir").write_text(portable_text, encoding="utf-8")

    print(f"Best objective: {best.aggregate_objective:.6g}")
    print(f"Best result saved to: {workdir / 'best_result.json'}")
    print(f"Portable netlist saved to: {workdir / 'best_portable.cir'}")


if __name__ == "__main__":
    main()
