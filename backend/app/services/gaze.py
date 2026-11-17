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

# MediaPipe FaceLandmarker indices (iris + eyelids).
LEFT_EYE_OUTER, LEFT_EYE_INNER, LEFT_IRIS = 33, 133, 468
LEFT_EYE_TOP, LEFT_EYE_BOTTOM = 159, 145
RIGHT_EYE_INNER, RIGHT_EYE_OUTER, RIGHT_IRIS = 362, 263, 473
RIGHT_EYE_TOP, RIGHT_EYE_BOTTOM = 386, 374


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
    iris_x: float
    iris_y: float
    face_area_ratio: float
    calibrated: bool


class GazeEstimator:
    """
    Screen-space gaze cursor: iris-first with light head-pose assist.

    Expects a mirrored (selfie) frame. Looking left should move the cursor left.
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
        self._smooth_x = None
        self._smooth_y = None
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
        r = mat[:3, :3]
        yaw = float(np.degrees(np.arctan2(r[0, 2], r[2, 2] + 1e-8)))
        pitch = float(np.degrees(np.arcsin(np.clip(-r[1, 2], -1.0, 1.0))))
        return yaw, pitch

    @staticmethod
    def _one_eye(
        landmarks,
        iris_idx: int,
        outer_idx: int,
        inner_idx: int,
        top_idx: int,
        bottom_idx: int,
    ) -> tuple[float, float]:
        iris = landmarks[iris_idx]
        outer = landmarks[outer_idx]
        inner = landmarks[inner_idx]
        top = landmarks[top_idx]
        bottom = landmarks[bottom_idx]

        # Eye-center frame: x in [-1, 1] from outer→inner, y from top→bottom.
        eye_cx = (outer.x + inner.x) / 2.0
        eye_cy = (top.y + bottom.y) / 2.0
        eye_w = abs(inner.x - outer.x) + 1e-6
        eye_h = abs(bottom.y - top.y) + 1e-6

        # Positive = iris toward +image X / +image Y (right / down in the frame).
        hx = (iris.x - eye_cx) / (eye_w * 0.5)
        hy = (iris.y - eye_cy) / (eye_h * 0.5)
        return float(np.clip(hx, -1.5, 1.5)), float(np.clip(hy, -1.5, 1.5))

    def _iris_offsets(self, landmarks) -> tuple[float, float]:
        try:
            lx, ly = self._one_eye(
                landmarks, LEFT_IRIS, LEFT_EYE_OUTER, LEFT_EYE_INNER, LEFT_EYE_TOP, LEFT_EYE_BOTTOM
            )
            rx, ry = self._one_eye(
                landmarks,
                RIGHT_IRIS,
                RIGHT_EYE_OUTER,
                RIGHT_EYE_INNER,
                RIGHT_EYE_TOP,
                RIGHT_EYE_BOTTOM,
            )
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

        dyaw = yaw - yaw0
        dpitch = pitch - pitch0
        diris_x = iris_x - iris_x0
        diris_y = iris_y - iris_y0

        # Iris-first screen mapping. On a mirrored selfie frame, iris moving right in the
        # image means looking toward the right side of the monitor → increase nx.
        head_x = dyaw / max(settings.gaze_yaw_range_deg, 1.0)
        head_y = dpitch / max(settings.gaze_pitch_range_deg, 1.0)
        nx = 0.5 + (
            diris_x * settings.gaze_iris_weight
            + head_x * settings.gaze_head_weight
        ) * settings.gaze_x_sign
        ny = 0.5 + (
            diris_y * settings.gaze_iris_weight
            + head_y * settings.gaze_head_weight
        ) * settings.gaze_y_sign
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
            iris_x=diris_x,
            iris_y=diris_y,
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
