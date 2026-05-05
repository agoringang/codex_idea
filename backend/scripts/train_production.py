from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ml_pipeline import train_artifact

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--output-dir", default=Path("models/racequant"), type=Path)
    parser.add_argument("--seed", default=42, type=int)
    parser.add_argument(
        "--race-limit",
        default=0,
        type=int,
        help="Use the first N races for smoke training",
    )
    args = parser.parse_args()

    metrics = train_artifact(
        args.csv,
        args.output_dir,
        args.seed,
        race_limit=args.race_limit or None,
    )

    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
