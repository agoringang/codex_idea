from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.schemas import IngestRequest, IngestResponse
from app.storage.tables import write_table


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [
        str(col).strip().lower().replace(" ", "_").replace("-", "_").replace("/", "_")
        for col in out.columns
    ]
    return out


def ingest_csv(request: IngestRequest) -> IngestResponse:
    path = Path(request.csv_path)
    if not path.is_absolute():
        path = Path.cwd() / path

    warnings: list[str] = []
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    df = pd.read_csv(path)
    df = _normalize_columns(df)

    race_col = request.race_id_column.lower()
    horse_col = request.horse_column.lower()
    if race_col not in df.columns:
        warnings.append(f"race id column '{race_col}' was not found.")
    if horse_col not in df.columns:
        warnings.append(f"horse column '{horse_col}' was not found.")

    output = request.output_name
    if not output.endswith(".parquet"):
        output = f"{output}.parquet"

    table = write_table(df, output, kind="normalized")
    return IngestResponse(table=table, warnings=warnings)
