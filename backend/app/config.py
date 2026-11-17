from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PW_", env_file=".env", extra="ignore")

    app_name: str = "ProductWatch"
    database_url: str = f"sqlite:///{(BACKEND_ROOT / 'data' / 'productwatch.db').as_posix()}"
    models_dir: Path = BACKEND_ROOT / "models"
    data_dir: Path = BACKEND_ROOT / "data"

    # Face matching
    face_match_threshold: float = 0.35  # cosine distance; lower = stricter
    enroll_sample_count: int = 12

    # Interest / gaze
    dwell_seconds: float = 1.5
    weight_bump: float = 5.0
    weight_cap: float = 100.0
    gaze_hit_radius_px: float = 40.0
    camera_id_default: str = "webcam-0"

    # Discounts
    personalized_min_weight: float = 15.0
    competitor_offer_percent: float = 10.0
    personalized_offer_percent: float = 15.0


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.models_dir.mkdir(parents=True, exist_ok=True)
