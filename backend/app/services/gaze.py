from __future__ import annotations

from dataclasses import dataclass

import cv2
import mediapipe as mp
import numpy as np

from backend.app.config import settings


@dataclass
class GazeHit:
    x: float
    y: float
    yaw: float
    pitch: float
    face_area_ratio: float


class GazeEstimator:
    """
    Head-pose gaze proxy using MediaPipe Face Mesh.
    Projects a ray from the face onto the image plane as an interest point.
    """

    def __init__(self) -> None:
        self._mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        # Approximate 3D model points for solvePnP (nose tip, chin, eyes, mouth).
        self._model_points = np.array(
            [
                (0.0, 0.0, 0.0),  # nose tip
                (0.0, -63.6, -12.5),  # chin
                (-43.3, 32.7, -26.0),  # left eye outer
                (43.3, 32.7, -26.0),  # right eye outer
                (-28.9, -28.9, -24.1),  # left mouth
                (28.9, -28.9, -24.1),  # right mouth
            ],
            dtype=np.float64,
        )
        self._landmark_ids = [1, 152, 33, 263, 61, 291]

    def close(self) -> None:
        self._mesh.close()

    def estimate(self, frame_bgr: np.ndarray) -> GazeHit | None:
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self._mesh.process(rgb)
        if not result.multi_face_landmarks:
            return None

        landmarks = result.multi_face_landmarks[0].landmark
        image_points = np.array(
            [(landmarks[i].x * w, landmarks[i].y * h) for i in self._landmark_ids],
            dtype=np.float64,
        )
        focal = w
        cam_matrix = np.array(
            [[focal, 0, w / 2], [0, focal, h / 2], [0, 0, 1]],
            dtype=np.float64,
        )
        dist = np.zeros((4, 1))
        ok, rvec, tvec = cv2.solvePnP(
            self._model_points, image_points, cam_matrix, dist, flags=cv2.SOLVEPNP_ITERATIVE
        )
        if not ok:
            return None

        rot, _ = cv2.Rodrigues(rvec)
        # Camera-space forward axis from head rotation.
        forward = rot @ np.array([0.0, 0.0, -1.0])
        yaw = float(np.degrees(np.arctan2(forward[0], forward[2])))
        pitch = float(np.degrees(np.arcsin(np.clip(-forward[1], -1.0, 1.0))))

        nose = image_points[0]
        # Map yaw/pitch onto the frame as a gaze cursor (hackathon aisle sim).
        gaze_x = float(np.clip(nose[0] + yaw * (w / 60.0), 0, w - 1))
        gaze_y = float(np.clip(nose[1] + pitch * (h / 60.0), 0, h - 1))

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
        # Soft hit: nearest zone center within radius.
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
