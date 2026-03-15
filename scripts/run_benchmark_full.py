#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> None:
    print(f"$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(cwd), check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {proc.returncode}: {' '.join(cmd)}")


def _require_path(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing required {label}: {path}")


def _preflight(repo_root: Path, ngspice_cmd: str) -> None:
    _require_path(repo_root / "scripts" / "generate_targets.py", "script")
    _require_path(repo_root / "scripts" / "generate_benchmark_dataset.py", "script")
    _require_path(repo_root / "scripts" / "evaluate_identification_baselines.py", "script")
    _require_path(repo_root / "scripts" / "optimizer.py", "script")
    _require_path(repo_root / "scripts" / "plot_benchmark_insights.py", "script")
    _require_path(repo_root / "scripts" / "plot_benchmark_deep_dive.py", "script")
    _require_path(repo_root / "templates" / "hardware_portable_ccp.cir.tmpl", "portable template")
    _require_path(repo_root / "templates" / "hardware_portable_icp_bias.cir.tmpl", "portable template")

    if "/" in ngspice_cmd:
        p = Path(ngspice_cmd)
        if not p.exists():
            raise FileNotFoundError(f"ngspice executable not found: {p}")
    else:
        resolved = shutil.which(ngspice_cmd)
        if resolved is None:
            raise FileNotFoundError(
                f"ngspice executable '{ngspice_cmd}' is not in PATH. "
                "Install ngspice (e.g., `brew install ngspice`) or pass --ngspice /path/to/ngspice."
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--python", type=str, default=sys.executable)
    parser.add_argument("--ngspice", type=str, default="ngspice")
    parser.add_argument("--benchmark-root", type=Path, default=Path("benchmark"))
    parser.add_argument("--fig-outdir", type=Path, default=Path("results/benchmark_figures"))
    parser.add_argument("--skip-optimizer", action="store_true")
    parser.add_argument("--skip-deep-dive", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    py = args.python
    bench_root = args.benchmark_root
    fig_out = args.fig_outdir

    _preflight(repo_root, args.ngspice)
    print("Preflight check: OK")

    _run([py, "scripts/generate_targets.py", "--outdir", "data"], repo_root)
    _run([py, "scripts/generate_benchmark_dataset.py", "--repo-root", ".", "--out-root", str(bench_root)], repo_root)
    _run(
        [
            py,
            "scripts/evaluate_identification_baselines.py",
            "--benchmark-root",
            str(bench_root),
            "--outdir",
            str(bench_root / "baselines"),
        ],
        repo_root,
    )

    if not args.skip_optimizer:
        _run(
            [
                py,
                "scripts/optimizer.py",
                "--config",
                "configs/design_space_ccp.yaml",
                "--workdir",
                "results/ccp_run",
                "--ngspice",
                args.ngspice,
            ],
            repo_root,
        )
        _run(
            [
                py,
                "scripts/optimizer.py",
                "--config",
                "configs/design_space_icp_bias.yaml",
                "--workdir",
                "results/icp_bias_run",
                "--ngspice",
                args.ngspice,
            ],
            repo_root,
        )

    _run(
        [
            py,
            "scripts/plot_benchmark_insights.py",
            "--benchmark-root",
            str(bench_root),
            "--outdir",
            str(fig_out),
        ],
        repo_root,
    )

    if not args.skip_deep_dive:
        _run(
            [
                py,
                "scripts/plot_benchmark_deep_dive.py",
                "--benchmark-root",
                str(bench_root),
                "--repo-root",
                ".",
                "--outdir",
                str(fig_out),
            ],
            repo_root,
        )

    print("Benchmark pipeline completed successfully.")
    print(f"- Benchmark root: {repo_root / bench_root}")
    print(f"- Figure output: {repo_root / fig_out}")


if __name__ == "__main__":
    main()
