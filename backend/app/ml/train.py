from __future__ import annotations

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from app.core.config import get_settings
from app.core.schemas import TrainRequest, TrainResponse
from app.storage.tables import read_table


DROP_COLUMNS = {
    "race_id",
    "race_date",
    "horse_id",
    "horse_name",
    "number",
    "finish_position",
    "is_win",
    "is_place",
}


def _safe_auc(y_true, proba) -> float | None:
    try:
        if len(set(y_true)) < 2:
            return None
        return float(roc_auc_score(y_true, proba))
    except Exception:
        return None


def train_model(request: TrainRequest) -> TrainResponse:
    settings = get_settings()
    df = read_table(request.feature_table, kind="features").copy()

    warnings: list[str] = []
    if request.target_column not in df.columns:
        raise ValueError(f"target column '{request.target_column}' not found")

    df = df.dropna(subset=[request.target_column])
    y = pd.to_numeric(df[request.target_column], errors="coerce").fillna(0).astype(int)

    feature_cols = [c for c in df.columns if c not in DROP_COLUMNS]
    X = df[feature_cols].copy()

    numeric_cols = [c for c in X.columns if pd.api.types.is_numeric_dtype(X[c])]
    categorical_cols = [c for c in X.columns if c not in numeric_cols]

    if len(df) < 200:
        warnings.append("Rows are fewer than 200. This model is only a smoke-test baseline.")

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", SimpleImputer(strategy="median"), numeric_cols),
            ("cat", Pipeline([
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(handle_unknown="ignore")),
            ]), categorical_cols),
        ],
        remainder="drop",
    )

    model = HistGradientBoostingClassifier(
        learning_rate=0.06,
        max_leaf_nodes=31,
        l2_regularization=0.01,
        random_state=42,
    )

    pipeline = Pipeline([("prep", preprocessor), ("model", model)])

    if len(set(y)) < 2:
        warnings.append("Target has only one class. Model training was skipped.")
        raise ValueError("target must include both positive and negative labels")

    stratify = y if y.value_counts().min() >= 2 else None
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, shuffle=True, stratify=stratify, random_state=42
    )

    pipeline.fit(X_train, y_train)
    pred = pipeline.predict(X_test)
    proba = pipeline.predict_proba(X_test)[:, 1]

    model_dir = settings.model_dir / request.model_name
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "latest.joblib"
    joblib.dump({"pipeline": pipeline, "features": feature_cols, "target": request.target_column}, model_path)

    return TrainResponse(
        model_path=str(model_path),
        rows=int(len(df)),
        auc=_safe_auc(y_test, proba),
        accuracy=float(accuracy_score(y_test, pred)),
        features=feature_cols,
        warnings=warnings,
    )
