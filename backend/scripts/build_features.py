from __future__ import annotations

import argparse

from app.ml.features import build_runner_features


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-table", default="runners.parquet")
    parser.add_argument("--output-table", default="runners_features.parquet")
    args = parser.parse_args()
    res = build_runner_features(args.input_table, args.output_table)
    print(res.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
