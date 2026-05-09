from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replace the JRA segment in a production artifact with a JRA-specialist artifact."
    )
    parser.add_argument("--base-artifact", type=Path, default=Path("models/racequant_daily/holdout_artifact.joblib"))
    parser.add_argument("--jra-artifact", type=Path, required=True)
    parser.add_argument("--output-artifact", type=Path, default=Path("models/racequant_daily/holdout_artifact.joblib"))
    parser.add_argument("--output-metrics", type=Path, default=Path("models/racequant_daily/holdout_experiment.json"))
    return parser


def segment_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    metrics = artifact.get("metrics") if isinstance(artifact.get("metrics"), dict) else {}
    return {
        "models": artifact.get("models", {}),
        "metrics": {
            "best": metrics.get("best", {}),
            "rank_holdout_2026": metrics.get("rank_holdout_2026", {}),
            "risk_router": metrics.get("risk_router", {}),
            "feature_mode": metrics.get("feature_mode"),
            "zoo_profile": metrics.get("zoo_profile"),
            "model_candidate_count": metrics.get("model_candidate_count"),
            "split": metrics.get("split", {}),
        },
        "numeric_features": artifact.get("numeric_features", []),
        "categorical_features": artifact.get("categorical_features", []),
    }


def main() -> None:
    args = build_parser().parse_args()
    base = joblib.load(args.base_artifact)
    jra = joblib.load(args.jra_artifact)
    if not isinstance(base, dict) or not isinstance(jra, dict):
        raise TypeError("Both artifacts must be joblib dictionaries.")

    segments = base.setdefault("segment_models", {})
    if not isinstance(segments, dict):
        raise TypeError("base segment_models must be a dictionary")
    segments["JRA"] = segment_payload(jra)

    base_metrics = base.get("metrics") if isinstance(base.get("metrics"), dict) else {}
    jra_metrics = jra.get("metrics") if isinstance(jra.get("metrics"), dict) else {}
    base_metrics["updated_at"] = datetime.now(timezone.utc).isoformat()
    base_metrics["jra_segment_source"] = str(args.jra_artifact)
    base_metrics.setdefault("segment_metrics", {})
    if isinstance(base_metrics["segment_metrics"], dict):
        base_metrics["segment_metrics"]["JRA"] = {
            "best": jra_metrics.get("best", {}),
            "rank_holdout_2026": jra_metrics.get("rank_holdout_2026", {}),
            "risk_router": jra_metrics.get("risk_router", {}),
            "zoo_profile": jra_metrics.get("zoo_profile"),
            "model_candidate_count": jra_metrics.get("model_candidate_count"),
        }
    base["metrics"] = base_metrics

    args.output_artifact.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(base, args.output_artifact)
    if args.output_metrics:
        args.output_metrics.parent.mkdir(parents=True, exist_ok=True)
        args.output_metrics.write_text(
            json.dumps(base_metrics, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "status": "ok",
                "output_artifact": str(args.output_artifact),
                "output_metrics": str(args.output_metrics),
                "jra_model_candidate_count": jra_metrics.get("model_candidate_count"),
                "jra_rank_holdout_2026": jra_metrics.get("rank_holdout_2026", {}),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
