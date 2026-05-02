from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def write_status(path: Path, **payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_step(args: list[str], status_path: Path, stage: str) -> None:
    write_status(status_path, stage=stage, command=args, state="running")
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)
    write_status(status_path, stage=stage, command=args, state="completed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the staged netkeiba collection pipeline.")
    parser.add_argument("--start-year", default=2006, type=int)
    parser.add_argument("--end-year", default=2026, type=int)
    parser.add_argument("--end-date", default="2026-05-02")
    parser.add_argument("--delay-seconds", default=10.0, type=float)
    parser.add_argument("--jitter-seconds", default=3.0, type=float)
    parser.add_argument("--list-url-file", default=Path("data/netkeiba_list_urls.txt"), type=Path)
    parser.add_argument("--race-url-file", default=Path("data/netkeiba_race_urls.txt"), type=Path)
    parser.add_argument("--output-csv", default=Path("data/netkeiba_race_history.csv"), type=Path)
    parser.add_argument("--status", default=Path("runtime/netkeiba_collect_status.json"), type=Path)
    parser.add_argument("--skip-race-fetch", action="store_true")
    parser.add_argument("--train-after", action="store_true")
    args = parser.parse_args()

    write_status(
        args.status,
        state="started",
        stage="init",
        start_year=args.start_year,
        end_year=args.end_year,
        end_date=args.end_date,
    )
    run_step(
        [
            "scripts/netkeiba_generate_list_urls.py",
            "--start-year",
            str(args.start_year),
            "--end-year",
            str(args.end_year),
            "--end-date",
            args.end_date,
            "--output",
            str(args.list_url_file),
        ],
        args.status,
        "generate_list_urls",
    )
    run_step(
        [
            "scripts/netkeiba_fetch.py",
            "--url-file",
            str(args.list_url_file),
            "--output-dir",
            "raw/netkeiba/list_html",
            "--manifest",
            "raw/netkeiba/list_manifest.csv",
            "--delay-seconds",
            str(args.delay_seconds),
            "--jitter-seconds",
            str(args.jitter_seconds),
        ],
        args.status,
        "fetch_daily_lists",
    )
    run_step(
        [
            "scripts/netkeiba_extract_race_urls.py",
            "--html-dir",
            "raw/netkeiba/list_html",
            "--output",
            str(args.race_url_file),
        ],
        args.status,
        "extract_race_urls",
    )

    if not args.skip_race_fetch:
        run_step(
            [
                "scripts/netkeiba_fetch.py",
                "--url-file",
                str(args.race_url_file),
                "--output-dir",
                "raw/netkeiba/html",
                "--manifest",
                "raw/netkeiba/race_manifest.csv",
                "--delay-seconds",
                str(args.delay_seconds),
                "--jitter-seconds",
                str(args.jitter_seconds),
            ],
            args.status,
            "fetch_race_pages",
        )
        run_step(
            [
                "scripts/netkeiba_parse.py",
                "--html-dir",
                "raw/netkeiba/html",
                "--output",
                str(args.output_csv),
            ],
            args.status,
            "parse_race_pages",
        )

    if args.train_after and args.output_csv.exists():
        run_step(
            [
                "scripts/train_production.py",
                "--csv",
                str(args.output_csv),
                "--output-dir",
                "models/racequant",
            ],
            args.status,
            "train_model",
        )

    write_status(args.status, state="completed", stage="done")


if __name__ == "__main__":
    main()
