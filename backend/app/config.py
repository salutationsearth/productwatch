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
    outbox_dir: Path = BACKEND_ROOT / "data" / "outbox"
    public_base_url: str = "http://127.0.0.1:8000"

    # Face matching
    face_match_threshold: float = 0.35  # cosine distance; lower = stricter
    enroll_sample_count: int = 12

    # Interest / gaze
    dwell_seconds: float = 1.5
    weight_bump: float = 5.0
    weight_cap: float = 100.0
    gaze_hit_radius_px: float = 100.0
    camera_id_default: str = "webcam-0"
    zone_ref_width: float = 1280.0
    zone_ref_height: float = 720.0
    gaze_yaw_range_deg: float = 16.0
    gaze_pitch_range_deg: float = 12.0
    gaze_head_weight: float = 1.0
    gaze_iris_weight: float = 0.18
    gaze_iris_fade_yaw_deg: float = 6.0
    gaze_iris_fade_pitch_deg: float = 5.0
    gaze_smooth: float = 0.4
    gaze_calib_frames: int = 20
    gaze_x_sign: float = 1.0
    gaze_y_sign: float = 1.0
    aisle_fullscreen: bool = True

    # Discounts
    personalized_min_weight: float = 15.0
    competitor_offer_percent: float = 10.0
    personalized_offer_percent: float = 15.0

    # Marketing agent
    agent_enabled: bool = True
    agent_poll_seconds: float = 20.0
    agent_min_interest_weight: float = 15.0
    agent_min_hours_since_interest: float = 0.02  # ~1 min — low for demo; raise in prod
    agent_max_hours_since_interest: float = 72.0
    agent_cooldown_hours_per_user: float = 0.05  # ~3 min demo cooldown
    agent_cooldown_hours_per_product: float = 12.0
    # LLM drafting: mock (default, no API) | openai
    llm_provider: str = "mock"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    # Email delivery: outbox (default) | resend | smtp
    email_provider: str = "outbox"
    resend_api_key: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    marketing_from_name: str = "ProductWatch Rewards"
    marketing_from_email: str = "rewards@productwatch.local"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.models_dir.mkdir(parents=True, exist_ok=True)
settings.outbox_dir.mkdir(parents=True, exist_ok=True)
