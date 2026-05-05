from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "UmaLab API"
    app_version: str = "0.2.0"
    data_dir: Path = Path("data")
    raw_dir: Path = Path("data/raw")
    normalized_dir: Path = Path("data/normalized")
    feature_dir: Path = Path("data/features")
    model_dir: Path = Path("models")
    backtest_dir: Path = Path("backtests")

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
