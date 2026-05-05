from __future__ import annotations

import argparse

from app.core.schemas import TrainRequest
from app.ml.train import train_model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-table", default="runners_features.parquet")
    parser.add_argument("--target-column", default="is_win")
    parser.add_argument("--model-name", default="win_model")
    args = parser.parse_args()

    res = train_model(
        TrainRequest(
            feature_table=args.feature_table,
            target_column=args.target_column,
            model_name=args.model_name,
        )
    )
    print(res.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
