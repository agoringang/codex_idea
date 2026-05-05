from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from app.core.config import get_settings
from app.core.schemas import DatasetSummary


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parquet_summary(path: Path) -> DatasetSummary:
    if not path.exists():
        return DatasetSummary(name=path.name, path=str(path), rows=0, columns=[], updated_at=None)

    con = duckdb.connect(database=":memory:")
    row_count = con.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone()[0]
    columns = [row[0] for row in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()]
    updated_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    return DatasetSummary(name=path.name, path=str(path), rows=int(row_count), columns=columns, updated_at=updated_at)


def list_parquet_tables(directory: Path) -> list[DatasetSummary]:
    return [parquet_summary(path) for path in sorted(directory.glob("*.parquet"))]


def read_table(name: str, kind: str = "features") -> pd.DataFrame:
    settings = get_settings()
    base = settings.feature_dir if kind == "features" else settings.normalized_dir
    path = base / name
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist")
    return pd.read_parquet(path)


def write_table(df: pd.DataFrame, name: str, kind: str = "normalized") -> DatasetSummary:
    settings = get_settings()
    base = settings.feature_dir if kind == "features" else settings.normalized_dir
    base.mkdir(parents=True, exist_ok=True)
    path = base / name
    df.to_parquet(path, index=False)
    manifest = base / "_manifest.json"
    payload = {}
    if manifest.exists():
        payload = json.loads(manifest.read_text())
    payload[name] = {"path": str(path), "rows": int(len(df)), "updated_at": _utc_now()}
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return parquet_summary(path)
