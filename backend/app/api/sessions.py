from fastapi import APIRouter

router = APIRouter(prefix="/session", tags=["session"])


@router.get("/aisle/info")
def aisle_info() -> dict[str, str]:
    """Aisle CV runs on a local demo machine and posts to /api/aisle/* — no server webcam."""
    return {
        "message": (
            "Run the local aisle demo on your PC: "
            "python -m backend.cv.webcam_aisle --server https://productwatch.jacob-yu.com"
        ),
        "bootstrap": "/api/aisle/bootstrap",
        "interest": "/api/aisle/interest",
    }
