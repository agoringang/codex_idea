from __future__ import annotations

import argparse
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.feature_catalog import CATEGORICAL_FEATURES, NUMERIC_FEATURES


def build_pipeline() -> Pipeline:
    numeric = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
        ]
    )
    categorical = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ("numeric", numeric, NUMERIC_FEATURES),
            ("categorical", categorical, CATEGORICAL_FEATURES),
        ]
    )

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "model",
                HistGradientBoostingClassifier(
                    learning_rate=0.045,
                    max_leaf_nodes=31,
                    l2_regularization=0.08,
                    random_state=42,
                ),
            ),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--output", default=Path("models/baseline.joblib"), type=Path)
    args = parser.parse_args()

    frame = pd.read_csv(args.csv)
    if "is_win" not in frame:
        raise ValueError("missing required target column: is_win")
    for column in NUMERIC_FEATURES:
        if column not in frame:
            frame[column] = pd.NA
    for column in CATEGORICAL_FEATURES:
        if column not in frame:
            frame[column] = "unknown"

    x_train, x_test, y_train, y_test = train_test_split(
        frame[[*NUMERIC_FEATURES, *CATEGORICAL_FEATURES]],
        frame["is_win"],
        test_size=0.2,
        random_state=42,
        stratify=frame["is_win"],
    )

    pipeline = build_pipeline()
    pipeline.fit(x_train, y_train)

    probabilities = pipeline.predict_proba(x_test)[:, 1]
    metrics = {
        "auc": roc_auc_score(y_test, probabilities),
        "log_loss": log_loss(y_test, probabilities),
        "rows": len(frame),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": pipeline, "metrics": metrics}, args.output)
    print(metrics)


if __name__ == "__main__":
    main()
