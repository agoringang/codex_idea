from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "UmaLab API"
    app_version: str = "0.2.0"
    data_dir: Path = BACKEND_ROOT / "data"
    raw_dir: Path = BACKEND_ROOT / "data/raw"
    normalized_dir: Path = BACKEND_ROOT / "data/normalized"
    feature_dir: Path = BACKEND_ROOT / "data/features"
    model_dir: Path = BACKEND_ROOT / "models"
    backtest_dir: Path = BACKEND_ROOT / "backtests"

    class Config:
        env_prefix = "UMALAB_"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    for path in [
        settings.data_dir,
        settings.raw_dir,
        settings.normalized_dir,
        settings.feature_dir,
        settings.model_dir,
        settings.backtest_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)
    return settings
