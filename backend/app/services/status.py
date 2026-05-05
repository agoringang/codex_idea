from __future__ import annotations

from app.core.config import get_settings
from app.core.schemas import PipelineStatus
from app.storage.tables import list_parquet_tables


def get_status() -> PipelineStatus:
    settings = get_settings()
    raw_files = sorted(str(p) for p in settings.raw_dir.glob("**/*") if p.is_file())
    normalized = list_parquet_tables(settings.normalized_dir)
    features = list_parquet_tables(settings.feature_dir)
    latest = settings.model_dir / "win_model" / "latest.joblib"

    message = (
        "Ready. API will read cached parquet/model artifacts only."
        if features or normalized
        else "No normalized data yet. Put CSV under backend/data/raw and run ingest."
    )

    return PipelineStatus(
        raw_files=raw_files[:50],
        normalized_tables=normalized,
        feature_tables=features,
        latest_model=str(latest) if latest.exists() else None,
        message=message,
    )
