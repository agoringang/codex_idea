from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRAIN_CSV = BACKEND_ROOT / "data" / "keiba_history_normalized.csv"
DEFAULT_HOLDOUT_CSV = BACKEND_ROOT / "data" / "netkeiba_2026_enriched.csv"
DEFAULT_OUTPUT_DIR = BACKEND_ROOT / "models" / "racequant_daily"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_command(args: list[str], *, cwd: Path) -> None:
    print(" ".join(args), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest latest races, then retrain the 10-model UmaLab zoo with 2026 holdout validation."
    )
    parser.add_argument("--train-csv", type=Path, default=DEFAULT_TRAIN_CSV)
    parser.add_argument("--holdout-csv", type=Path, default=DEFAULT_HOLDOUT_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--days", type=int, default=2)
    parser.add_argument("--days-ahead", type=int, default=2)
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument("--feature-mode", choices=["all", "anti_market"], default="anti_market")
    parser.add_argument("--market-weight-cap", type=float, default=0.2)
    parser.add_argument("--market-weight-step", type=float, default=0.05)
    parser.add_argument("--favorite-rate-cap", type=float, default=0.74)
    parser.add_argument("--favorite-penalty", type=float, default=0.36)
    parser.add_argument("--max-iter", type=int, default=80)
    parser.add_argument("--train-race-limit", type=int, default=0)
    parser.add_argument("--skip-hgb", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    python = sys.executable

    if not args.skip_ingest:
        run_command(
            [
                python,
                "scripts/scrape_netkeiba_2026.py",
                "--days",
                str(args.days),
                "--days-ahead",
                str(args.days_ahead),
                "--base-csv",
                str(args.train_csv),
                "--output",
                str(BACKEND_ROOT / "data" / "netkeiba_2026_normalized.csv"),
                "--enriched-output",
                str(args.holdout_csv),
                "--enriched-combined-output",
                str(BACKEND_ROOT / "data" / "keiba_history_with_2026_enriched.csv"),
            ],
            cwd=BACKEND_ROOT,
        )

    train_args = [
        python,
        "scripts/experiment_holdout_2026.py",
        "--train-csv",
        str(args.train_csv),
        "--holdout-csv",
        str(args.holdout_csv),
        "--output-dir",
        str(args.output_dir),
        "--segment-by-market",
        "--feature-mode",
        args.feature_mode,
        "--market-weight-cap",
        str(args.market_weight_cap),
        "--market-weight-step",
        str(args.market_weight_step),
        "--favorite-rate-cap",
        str(args.favorite_rate_cap),
        "--favorite-penalty",
        str(args.favorite_penalty),
        "--max-iter",
        str(args.max_iter),
    ]
    if args.train_race_limit > 0:
        train_args.extend(["--train-race-limit", str(args.train_race_limit)])
    if args.skip_hgb:
        train_args.append("--skip-hgb")
    run_command(train_args, cwd=BACKEND_ROOT)

    artifact = args.output_dir / "holdout_artifact.joblib"
    metrics = args.output_dir / "holdout_experiment.json"
    manifest = args.output_dir / "model_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "artifact_path": str(artifact),
                "metrics_path": str(metrics),
                "sha256": sha256_file(artifact) if artifact.exists() else None,
                "train_csv": str(args.train_csv),
                "holdout_csv": str(args.holdout_csv),
                "feature_mode": args.feature_mode,
                "market_weight_cap": args.market_weight_cap,
                "favorite_rate_cap": args.favorite_rate_cap,
                "favorite_penalty": args.favorite_penalty,
                "model_count": 10 if not args.skip_hgb else 6,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(manifest.read_text(encoding="utf-8"), flush=True)


if __name__ == "__main__":
    main()
