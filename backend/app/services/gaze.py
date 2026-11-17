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

# MediaPipe FaceLandmarker indices (with iris refinement).
NOSE_TIP = 1
LEFT_EYE_OUTER, LEFT_EYE_INNER, LEFT_IRIS = 33, 133, 468
RIGHT_EYE_INNER, RIGHT_EYE_OUTER, RIGHT_IRIS = 362, 263, 473


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
    calibrated: bool


class GazeEstimator:
    """
    Screen-space gaze cursor for the webcam aisle demo.

    Maps head pose + iris offset onto the full frame (not onto the nose).
    That way looking left/right/up/down moves the yellow dot across product zones.
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
        self._smooth_x: float | None = None
        self._smooth_y: float | None = None
        self._yaw0: float | None = None
        self._pitch0: float | None = None
        self._iris_x0: float | None = None
        self._iris_y0: float | None = None
        self._calib_yaw: list[float] = []
        self._calib_pitch: list[float] = []
        self._calib_iris_x: list[float] = []
        self._calib_iris_y: list[float] = []

    def close(self) -> None:
        self._landmarker.close()

    def reset_calibration(self) -> None:
        self._yaw0 = None
        self._pitch0 = None
        self._iris_x0 = None
        self._iris_y0 = None
        self._calib_yaw.clear()
        self._calib_pitch.clear()
        self._calib_iris_x.clear()
        self._calib_iris_y.clear()

    @property
    def is_calibrated(self) -> bool:
        return self._yaw0 is not None

    def _head_angles(self, result) -> tuple[float, float]:
        if not result.facial_transformation_matrixes:
            return 0.0, 0.0
        mat = np.asarray(result.facial_transformation_matrixes[0], dtype=np.float64)
        # Camera looks down -Z; face forward in model space is often -Z as well.
        r = mat[:3, :3]
        # Extract yaw/pitch from rotation matrix (YXZ-ish).
        yaw = float(np.degrees(np.arctan2(r[0, 2], r[2, 2] + 1e-8)))
        pitch = float(np.degrees(np.arcsin(np.clip(-r[1, 2], -1.0, 1.0))))
        return yaw, pitch

    @staticmethod
    def _iris_offsets(landmarks) -> tuple[float, float]:
        """Return eye-gaze offsets in roughly [-0.5, 0.5] (right/down positive in image)."""

        def ratio(iris_idx: int, outer_idx: int, inner_idx: int) -> tuple[float, float]:
            iris = landmarks[iris_idx]
            outer = landmarks[outer_idx]
            inner = landmarks[inner_idx]
            # Horizontal: 0 at outer, 1 at inner — center ~0.5.
            dx = (inner.x - outer.x) or 1e-6
            dy = (inner.y - outer.y) or 1e-6
            # Also use vertical span from eye corners average vs iris.
            hx = (iris.x - outer.x) / dx
            # Approximate vertical with eyelid-independent corner midline.
            mid_y = (outer.y + inner.y) / 2.0
            eye_h = abs(dx) * 0.35 + 1e-6
            hy = (iris.y - mid_y) / eye_h
            return hx - 0.5, hy

        try:
            lx, ly = ratio(LEFT_IRIS, LEFT_EYE_OUTER, LEFT_EYE_INNER)
            rx, ry = ratio(RIGHT_IRIS, RIGHT_EYE_OUTER, RIGHT_EYE_INNER)
            # Average both eyes. Image x grows right; looking right moves iris toward outer on left eye
            # and toward inner on right eye — averaging raw hx works surprisingly well after calibration.
            return (lx + rx) / 2.0, (ly + ry) / 2.0
        except (IndexError, AttributeError):
            return 0.0, 0.0

    def _maybe_calibrate(self, yaw: float, pitch: float, iris_x: float, iris_y: float) -> None:
        if self.is_calibrated:
            return
        self._calib_yaw.append(yaw)
        self._calib_pitch.append(pitch)
        self._calib_iris_x.append(iris_x)
        self._calib_iris_y.append(iris_y)
        need = max(8, int(settings.gaze_calib_frames))
        if len(self._calib_yaw) >= need:
            self._yaw0 = float(np.median(self._calib_yaw))
            self._pitch0 = float(np.median(self._calib_pitch))
            self._iris_x0 = float(np.median(self._calib_iris_x))
            self._iris_y0 = float(np.median(self._calib_iris_y))

    def estimate(self, frame_bgr: np.ndarray) -> GazeHit | None:
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        self._frame_ts_ms += 33
        result = self._landmarker.detect_for_video(mp_image, self._frame_ts_ms)
        if not result.face_landmarks:
            return None

        landmarks = result.face_landmarks[0]
        yaw, pitch = self._head_angles(result)
        iris_x, iris_y = self._iris_offsets(landmarks)
        self._maybe_calibrate(yaw, pitch, iris_x, iris_y)

        yaw0 = self._yaw0 if self._yaw0 is not None else yaw
        pitch0 = self._pitch0 if self._pitch0 is not None else pitch
        iris_x0 = self._iris_x0 if self._iris_x0 is not None else iris_x
        iris_y0 = self._iris_y0 if self._iris_y0 is not None else iris_y

        # Relative signals: turn head / look with eyes away from center calibration.
        dyaw = yaw - yaw0
        dpitch = pitch - pitch0
        diris_x = iris_x - iris_x0
        diris_y = iris_y - iris_y0

        # Combine into normalized screen coords. Head dominates coarse aim; iris fine-tunes.
        # Mirror X so turning your head to YOUR left aims at the left side of a mirrored preview.
        nx = 0.5 - (
            dyaw / max(settings.gaze_yaw_range_deg, 1.0) * settings.gaze_head_weight
            + diris_x * settings.gaze_iris_weight
        )
        ny = 0.5 + (
            dpitch / max(settings.gaze_pitch_range_deg, 1.0) * settings.gaze_head_weight
            + diris_y * settings.gaze_iris_weight
        )
        nx = float(np.clip(nx, 0.0, 1.0))
        ny = float(np.clip(ny, 0.0, 1.0))

        raw_x, raw_y = nx * (w - 1), ny * (h - 1)
        alpha = settings.gaze_smooth
        if self._smooth_x is None:
            self._smooth_x, self._smooth_y = raw_x, raw_y
        else:
            self._smooth_x = alpha * raw_x + (1 - alpha) * self._smooth_x
            self._smooth_y = alpha * raw_y + (1 - alpha) * self._smooth_y

        xs = [lm.x * w for lm in landmarks]
        ys = [lm.y * h for lm in landmarks]
        face_area_ratio = float(((max(xs) - min(xs)) * (max(ys) - min(ys))) / (w * h + 1e-8))

        return GazeHit(
            x=float(self._smooth_x),
            y=float(self._smooth_y),
            yaw=dyaw,
            pitch=dpitch,
            face_area_ratio=face_area_ratio,
            calibrated=self.is_calibrated,
        )


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
