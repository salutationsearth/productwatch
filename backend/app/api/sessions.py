from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.schemas import AisleSessionRequest, AisleSessionResult

router = APIRouter(prefix="/session", tags=["session"])


@router.post("/aisle/start", response_model=AisleSessionResult)
def start_aisle_session(
    payload: AisleSessionRequest,
    camera_index: int = 0,
    db: Session = Depends(get_db),
) -> AisleSessionResult:
    """
    Blocks while the server-side webcam aisle loop runs.
    Prefer the CLI (`python -m backend.cv.webcam_aisle`) for demos.
    """
    try:
        from backend.cv.webcam_aisle import run_aisle_session

        return run_aisle_session(
            db,
            camera_id=payload.camera_id,
            camera_index=camera_index,
            max_seconds=payload.max_seconds,
            force_user_id=payload.force_user_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
