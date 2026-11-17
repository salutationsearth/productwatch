"""
Local aisle computer-vision demo.

Runs webcam + gaze on YOUR machine, then POSTs interest events to the
hosted WatcherMart server (no camera on the VPS).

Example:
  python -m backend.cv.webcam_aisle --server https://productwatch.jacob-yu.com --user-id 1
"""

from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass

import cv2
import httpx
import numpy as np

from backend.app.config import settings
from backend.app.services.face import face_service
from backend.app.services.gaze import GazeEstimator, hit_product_zone

WINDOW_NAME = "WatcherMart — Aisle Interest (local → server)"


@dataclass
class _ZoneView:
    product_id: int
    x1: float
    y1: float
    x2: float
    y2: float
    label: str | None


@dataclass
class _RemoteFace:
    user_id: int
    name: str
    embedding: np.ndarray


class AisleServerClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-Aisle-Key": api_key}

    def bootstrap(self, camera_id: str) -> dict:
        r = httpx.get(
            f"{self.base_url}/api/aisle/bootstrap",
            params={"camera_id": camera_id},
            headers=self.headers,
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()

    def report_interest(self, payload: dict) -> dict:
        r = httpx.post(
            f"{self.base_url}/api/aisle/interest",
            json=payload,
            headers=self.headers,
            timeout=20.0,
        )
        r.raise_for_status()
        return r.json()


def _scale_and_mirror_zones(
    zones: list[dict],
    frame_w: int,
    frame_h: int,
    ref_w: float,
    ref_h: float,
) -> list[_ZoneView]:
    sx = frame_w / ref_w
    sy = frame_h / ref_h
    out: list[_ZoneView] = []
    for z in zones:
        x1 = z["x1"] * sx
        x2 = z["x2"] * sx
        y1 = z["y1"] * sy
        y2 = z["y2"] * sy
        out.append(
            _ZoneView(
                product_id=z["product_id"],
                x1=frame_w - 1 - x2,
                y1=y1,
                x2=frame_w - 1 - x1,
                y2=y2,
                label=z.get("label"),
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
        cv2.putText(
            frame,
            label,
            (int(z.x1) + 8, int(z.y1) + 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2,
        )


def _set_fullscreen(enabled: bool) -> None:
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    prop = cv2.WINDOW_FULLSCREEN if enabled else cv2.WINDOW_NORMAL
    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, prop)
    if not enabled:
        cv2.resizeWindow(WINDOW_NAME, 1280, 720)
        cv2.moveWindow(WINDOW_NAME, 80, 40)


def _match_local(embedding: np.ndarray, faces: list[_RemoteFace], threshold: float) -> int | None:
    best_id = None
    best_dist = float("inf")
    for face in faces:
        dist = face_service.cosine_distance(embedding, face.embedding)
        if dist < best_dist:
            best_dist = dist
            best_id = face.user_id
    if best_id is None or best_dist > threshold:
        return None
    return best_id


def run_aisle_session_remote(
    *,
    server_url: str,
    api_key: str,
    camera_id: str = "webcam-0",
    camera_index: int = 0,
    max_seconds: float | None = 60.0,
    force_user_id: int | None = None,
) -> dict:
    client = AisleServerClient(server_url, api_key)
    print(f"Fetching aisle bootstrap from {server_url} …", flush=True)
    boot = client.bootstrap(camera_id)
    zones_raw = boot["zones"]
    if not zones_raw:
        raise RuntimeError(
            f"No product zones for camera '{camera_id}' on server. Seed products on the VPS first."
        )

    products = {p["id"]: p["name"] for p in boot["products"]}
    ref_w = float(boot.get("zone_ref_width") or settings.zone_ref_width)
    ref_h = float(boot.get("zone_ref_height") or settings.zone_ref_height)
    dwell_seconds = float(boot.get("dwell_seconds") or settings.dwell_seconds)
    remote_faces = [
        _RemoteFace(
            user_id=f["user_id"],
            name=f["name"],
            embedding=np.asarray(f["embedding"], dtype=np.float32),
        )
        for f in boot.get("face_enrollments", [])
    ]
    print(
        f"Loaded {len(products)} products, {len(zones_raw)} zones, "
        f"{len(remote_faces)} face enrollments from server.",
        flush=True,
    )

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open local webcam index {camera_index}")
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
    last_weights: dict[int, float] = {}

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
            view_zones = _scale_and_mirror_zones(zones_raw, w, h, ref_w, ref_h)

            if matched_user is None and remote_faces and time.time() - last_identify > 1.0:
                emb = face_service.embed_largest(frame)
                if emb is not None:
                    uid = _match_local(emb, remote_faces, settings.face_match_threshold)
                    if uid is not None:
                        matched_user = uid
                        print(f"Matched shopper user_id={uid}", flush=True)
                last_identify = time.time()

            hit = gaze_est.estimate(frame)
            active_pid = None
            if hit is not None:
                zone = hit_product_zone(hit.x, hit.y, view_zones)
                cv2.drawMarker(
                    frame,
                    (int(hit.x), int(hit.y)),
                    (0, 255, 255),
                    markerType=cv2.MARKER_CROSS,
                    markerSize=28,
                    thickness=2,
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
                        if matched_user is not None and dwell >= dwell_seconds:
                            try:
                                result = client.report_interest(
                                    {
                                        "user_id": matched_user,
                                        "product_id": active_pid,
                                        "dwell_seconds": dwell,
                                        "camera_id": camera_id,
                                        "gaze_x": hit.x,
                                        "gaze_y": hit.y,
                                        "proximity": hit.face_area_ratio,
                                    }
                                )
                                events += 1
                                last_weights[active_pid] = float(result["weight"])
                                print(
                                    f"Sent interest → server: {result.get('product_name')} "
                                    f"weight={result['weight']:.1f}",
                                    flush=True,
                                )
                            except httpx.HTTPError as exc:
                                print(f"Failed to POST interest: {exc}", flush=True)
                            dwell_start[active_pid] = time.time()
                else:
                    current_zone_pid = None
                    dwell_start.clear()

            _draw_zones(frame, view_zones, products, active_pid)
            status = f"user={matched_user or 'unknown'} events={events} → {server_url}"
            cv2.putText(frame, status, (24, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            if hit is None or not hit.calibrated:
                hint = "Calibrating: look at the CENTER of the screen..."
                color = (0, 200, 255)
            else:
                hint = "Aim with your HEAD at a product.  C=recalibrate  F=fullscreen  Q=quit"
                color = (200, 200, 200)
            cv2.putText(frame, hint, (24, 74), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

            cv2.imshow(WINDOW_NAME, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:
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

    return {
        "matched_user_id": matched_user,
        "events_recorded": events,
        "last_weights": last_weights,
        "server": server_url,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Local aisle CV → remote WatcherMart server")
    parser.add_argument(
        "--server",
        default=os.getenv("PW_AISLE_SERVER", settings.public_base_url),
        help="WatcherMart server base URL",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("PW_AISLE_API_KEY", settings.aisle_api_key),
        help="Aisle API key (must match server PW_AISLE_API_KEY)",
    )
    parser.add_argument("--camera-id", default="webcam-0")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--seconds", type=float, default=0.0, help="0 = run until Q")
    parser.add_argument("--user-id", type=int, default=None, help="Skip face match; force this user")
    args = parser.parse_args()

    max_seconds = None if args.seconds <= 0 else args.seconds
    result = run_aisle_session_remote(
        server_url=args.server,
        api_key=args.api_key,
        camera_id=args.camera_id,
        camera_index=args.camera,
        max_seconds=max_seconds,
        force_user_id=args.user_id,
    )
    print(result, flush=True)


if __name__ == "__main__":
    main()
