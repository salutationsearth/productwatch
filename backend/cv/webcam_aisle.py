"""Local aisle CV demo — webcam on this machine, interest saved to the local DB."""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass

import cv2
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models import Product, ProductZone
from backend.app.schemas import AisleSessionResult
from backend.app.services.discounts import refresh_offers_for_user
from backend.app.services.face import face_service
from backend.app.services.gaze import GazeEstimator, hit_product_zone
from backend.app.services.interest import bump_interest, list_interests

WINDOW_NAME = "WatcherMart — Aisle Interest"


@dataclass
class _ZoneView:
    product_id: int
    x1: float
    y1: float
    x2: float
    y2: float
    label: str | None


def _scale_and_mirror_zones(zones: list[ProductZone], frame_w: int, frame_h: int) -> list[_ZoneView]:
    sx = frame_w / settings.zone_ref_width
    sy = frame_h / settings.zone_ref_height
    out: list[_ZoneView] = []
    for z in zones:
        x1, x2 = z.x1 * sx, z.x2 * sx
        y1, y2 = z.y1 * sy, z.y2 * sy
        out.append(
            _ZoneView(
                product_id=z.product_id,
                x1=frame_w - 1 - x2,
                y1=y1,
                x2=frame_w - 1 - x1,
                y2=y2,
                label=z.label,
            )
        )
    return out


def _draw_zones(frame, zones: list[_ZoneView], product_names: dict[int, str], active_pid: int | None):
    for z in zones:
        color = (40, 200, 80) if z.product_id == active_pid else (80, 80, 200)
        thickness = 3 if z.product_id == active_pid else 2
        cv2.rectangle(frame, (int(z.x1), int(z.y1)), (int(z.x2), int(z.y2)), color, thickness)
        overlay = frame.copy()
        cv2.rectangle(overlay, (int(z.x1), int(z.y1)), (int(z.x2), int(z.y2)), color, -1)
        cv2.addWeighted(overlay, 0.12, frame, 0.88, 0, frame)
        label = z.label or product_names.get(z.product_id, str(z.product_id))
        cv2.putText(frame, label, (int(z.x1) + 8, int(z.y1) + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)


def _set_fullscreen(enabled: bool) -> None:
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    prop = cv2.WINDOW_FULLSCREEN if enabled else cv2.WINDOW_NORMAL
    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, prop)
    if not enabled:
        cv2.resizeWindow(WINDOW_NAME, 1280, 720)
        cv2.moveWindow(WINDOW_NAME, 80, 40)


def run_aisle_session(
    db: Session,
    camera_id: str = "webcam-0",
    camera_index: int = 0,
    max_seconds: float | None = 60.0,
    force_user_id: int | None = None,
) -> AisleSessionResult:
    zones = db.query(ProductZone).filter(ProductZone.camera_id == camera_id).all()
    if not zones:
        raise RuntimeError(
            f"No product zones for '{camera_id}'. Run: python backend/scripts/seed_products.py"
        )

    products = {p.id: p.name for p in db.query(Product).all()}
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open webcam index {camera_index}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    gaze_est = GazeEstimator()
    matched_user: int | None = force_user_id
    dwell_start: dict[int, float] = {}
    current_zone_pid: int | None = None
    events = 0
    started = time.time()
    last_identify = 0.0
    fullscreen = settings.aisle_fullscreen
    _set_fullscreen(fullscreen)

    try:
        while True:
            if max_seconds is not None and (time.time() - started) > max_seconds:
                break
            ok, frame = cap.read()
            if not ok:
                continue
            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            view_zones = _scale_and_mirror_zones(zones, w, h)

            if matched_user is None and time.time() - last_identify > 1.0:
                emb = face_service.embed_largest(frame)
                if emb is not None:
                    uid, _ = face_service.match_user(db, emb)
                    if uid is not None:
                        matched_user = uid
                last_identify = time.time()

            hit = gaze_est.estimate(frame)
            active_pid = None
            if hit is not None:
                zone = hit_product_zone(hit.x, hit.y, view_zones)
                cv2.drawMarker(
                    frame, (int(hit.x), int(hit.y)), (0, 255, 255),
                    markerType=cv2.MARKER_CROSS, markerSize=28, thickness=2,
                )
                cv2.circle(frame, (int(hit.x), int(hit.y)), 7, (0, 255, 255), -1)
                if zone is not None:
                    active_pid = zone.product_id
                    if current_zone_pid != active_pid:
                        current_zone_pid = active_pid
                        dwell_start.clear()
                        dwell_start[active_pid] = time.time()
                    else:
                        dwell = time.time() - dwell_start.get(active_pid, time.time())
                        if matched_user is not None and dwell >= settings.dwell_seconds:
                            bump_interest(
                                db,
                                user_id=matched_user,
                                product_id=active_pid,
                                dwell_seconds=dwell,
                                camera_id=camera_id,
                                gaze_x=hit.x,
                                gaze_y=hit.y,
                                proximity=hit.face_area_ratio,
                            )
                            events += 1
                            dwell_start[active_pid] = time.time()
                else:
                    current_zone_pid = None
                    dwell_start.clear()

            _draw_zones(frame, view_zones, products, active_pid)
            cv2.putText(
                frame, f"user={matched_user or 'unknown'} events={events}",
                (24, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2,
            )
            hint = (
                "Calibrating: look at CENTER..."
                if hit is None or not hit.calibrated
                else "Aim with your HEAD.  C=recalibrate  F=fullscreen  Q=quit"
            )
            cv2.putText(frame, hint, (24, 74), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 2)
            cv2.imshow(WINDOW_NAME, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("c"):
                gaze_est.reset_calibration()
            if key == ord("f"):
                fullscreen = not fullscreen
                _set_fullscreen(fullscreen)
    finally:
        gaze_est.close()
        cap.release()
        cv2.destroyAllWindows()

    interests = []
    offers = []
    if matched_user is not None:
        interests = list_interests(db, matched_user)
        offers = refresh_offers_for_user(db, matched_user)
    return AisleSessionResult(
        matched_user_id=matched_user,
        events_recorded=events,
        interest_updates=interests,
        offers=offers,
    )


def main() -> None:
    from backend.app.db import SessionLocal, init_db

    parser = argparse.ArgumentParser(description="Local aisle interest session")
    parser.add_argument("--camera-id", default="webcam-0")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--seconds", type=float, default=0.0, help="0 = until Q")
    parser.add_argument("--user-id", type=int, default=None)
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        result = run_aisle_session(
            db,
            camera_id=args.camera_id,
            camera_index=args.camera,
            max_seconds=None if args.seconds <= 0 else args.seconds,
            force_user_id=args.user_id,
        )
        print(result.model_dump_json(indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
