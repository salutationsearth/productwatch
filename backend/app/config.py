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
    gaze_hit_radius_px: float = 100.0
    camera_id_default: str = "webcam-0"
    # Seed zones were authored for this reference frame size
    zone_ref_width: float = 1280.0
    zone_ref_height: float = 720.0
    # Screen-cursor mapping — head-primary; iris is a light assist near center
    gaze_yaw_range_deg: float = 16.0  # smaller = easier to reach screen edges with head
    gaze_pitch_range_deg: float = 12.0
    gaze_head_weight: float = 1.0
    gaze_iris_weight: float = 0.18
    # Fade iris assist as the head turns (iris deltas go wild under head rotation)
    gaze_iris_fade_yaw_deg: float = 6.0
    gaze_iris_fade_pitch_deg: float = 5.0
    gaze_smooth: float = 0.4
    gaze_calib_frames: int = 20
    # +1 = looking right moves cursor right on mirrored preview; set -1 if still inverted
    gaze_x_sign: float = 1.0
    gaze_y_sign: float = 1.0
    aisle_fullscreen: bool = True

    # Discounts
    personalized_min_weight: float = 15.0
    competitor_offer_percent: float = 10.0
    personalized_offer_percent: float = 15.0


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.models_dir.mkdir(parents=True, exist_ok=True)
