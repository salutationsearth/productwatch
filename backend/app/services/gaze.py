from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

from backend.app.config import settings

LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)


def _ensure_landmarker_model() -> Path:
    path = settings.models_dir / "face_landmarker.task"
    if path.exists() and path.stat().st_size > 0:
        return path
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(LANDMARKER_URL, path)
    return path


@dataclass
class GazeHit:
    x: float
    y: float
    yaw: float
    pitch: float
    face_area_ratio: float


class GazeEstimator:
    """
    Head-pose gaze proxy using MediaPipe Tasks FaceLandmarker.
    Projects a ray from the face onto the image plane as an interest point.
    """

    def __init__(self) -> None:
        model = _ensure_landmarker_model()
        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(model)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_facial_transformation_matrixes=True,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self._frame_ts_ms = 0

    def close(self) -> None:
        self._landmarker.close()

    def estimate(self, frame_bgr: np.ndarray) -> GazeHit | None:
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        self._frame_ts_ms += 33
        result = self._landmarker.detect_for_video(mp_image, self._frame_ts_ms)
        if not result.face_landmarks:
            return None

        landmarks = result.face_landmarks[0]
        nose = landmarks[1]
        nose_x, nose_y = nose.x * w, nose.y * h

        yaw = 0.0
        pitch = 0.0
        if result.facial_transformation_matrixes:
            mat = np.asarray(result.facial_transformation_matrixes[0], dtype=np.float64)
            # MediaPipe facial transform: rotation maps face axes into camera space.
            forward = mat[:3, :3] @ np.array([0.0, 0.0, -1.0])
            yaw = float(np.degrees(np.arctan2(forward[0], forward[2] + 1e-8)))
            pitch = float(np.degrees(np.arcsin(np.clip(-forward[1], -1.0, 1.0))))

        gaze_x = float(np.clip(nose_x + yaw * (w / 60.0), 0, w - 1))
        gaze_y = float(np.clip(nose_y + pitch * (h / 60.0), 0, h - 1))

        xs = [lm.x * w for lm in landmarks]
        ys = [lm.y * h for lm in landmarks]
        face_w = max(xs) - min(xs)
        face_h = max(ys) - min(ys)
        face_area_ratio = float((face_w * face_h) / (w * h + 1e-8))

        return GazeHit(x=gaze_x, y=gaze_y, yaw=yaw, pitch=pitch, face_area_ratio=face_area_ratio)


def point_in_zone(x: float, y: float, zone) -> bool:
    return zone.x1 <= x <= zone.x2 and zone.y1 <= y <= zone.y2


def hit_product_zone(x: float, y: float, zones: list) -> object | None:
    """Return the zone containing (x,y), preferring the smallest area on overlap."""
    hits = [z for z in zones if point_in_zone(x, y, z)]
    if not hits:
        best = None
        best_d = settings.gaze_hit_radius_px
        for z in zones:
            cx = (z.x1 + z.x2) / 2
            cy = (z.y1 + z.y2) / 2
            d = float(np.hypot(x - cx, y - cy))
            if d < best_d:
                best_d = d
                best = z
        return best
    hits.sort(key=lambda z: (z.x2 - z.x1) * (z.y2 - z.y1))
    return hits[0]
