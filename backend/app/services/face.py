from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models import FaceEmbedding, User

YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
SFACE_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_recognition_sface/face_recognition_sface_2021dec.onnx"
)


def _ensure_model(url: str, filename: str) -> Path:
    path = settings.models_dir / filename
    if path.exists() and path.stat().st_size > 0:
        return path
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, path)
    return path


class FaceService:
    """Face detect + embed via OpenCV YuNet + SFace (Windows-friendly ONNX)."""

    def __init__(self) -> None:
        self._detector: cv2.FaceDetectorYN | None = None
        self._recognizer: cv2.FaceRecognizerSF | None = None

    def _load(self) -> None:
        if self._detector is not None and self._recognizer is not None:
            return
        yunet = _ensure_model(YUNET_URL, "face_detection_yunet_2023mar.onnx")
        sface = _ensure_model(SFACE_URL, "face_recognition_sface_2021dec.onnx")
        self._detector = cv2.FaceDetectorYN.create(str(yunet), "", (320, 320), 0.6, 0.3, 5000)
        self._recognizer = cv2.FaceRecognizerSF.create(str(sface), "")

    def detect_faces(self, frame_bgr: np.ndarray) -> np.ndarray:
        self._load()
        assert self._detector is not None
        h, w = frame_bgr.shape[:2]
        self._detector.setInputSize((w, h))
        _, faces = self._detector.detect(frame_bgr)
        if faces is None:
            return np.empty((0, 15), dtype=np.float32)
        return faces

    def largest_face(self, frame_bgr: np.ndarray) -> np.ndarray | None:
        faces = self.detect_faces(frame_bgr)
        if len(faces) == 0:
            return None
        areas = faces[:, 2] * faces[:, 3]
        return faces[int(np.argmax(areas))]

    def embed_face(self, frame_bgr: np.ndarray, face: np.ndarray) -> np.ndarray:
        self._load()
        assert self._recognizer is not None
        aligned = self._recognizer.alignCrop(frame_bgr, face)
        feature = self._recognizer.feature(aligned)
        vec = np.asarray(feature, dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def embed_largest(self, frame_bgr: np.ndarray) -> np.ndarray | None:
        face = self.largest_face(frame_bgr)
        if face is None:
            return None
        return self.embed_face(frame_bgr, face)

    @staticmethod
    def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
        return float(1.0 - np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))

    def match_user(
        self,
        db: Session,
        embedding: np.ndarray,
        threshold: float | None = None,
    ) -> tuple[int | None, float]:
        threshold = settings.face_match_threshold if threshold is None else threshold
        best_user: int | None = None
        best_dist = float("inf")
        rows = db.query(FaceEmbedding).all()
        for row in rows:
            stored = np.asarray(json.loads(row.embedding), dtype=np.float32)
            dist = self.cosine_distance(embedding, stored)
            if dist < best_dist:
                best_dist = dist
                best_user = row.user_id
        if best_user is None or best_dist > threshold:
            return None, best_dist
        return best_user, best_dist

    def save_embedding(self, db: Session, user_id: int, embedding: np.ndarray) -> FaceEmbedding:
        user = db.get(User, user_id)
        if user is None:
            raise ValueError(f"User {user_id} not found")
        row = FaceEmbedding(user_id=user_id, embedding=json.dumps(embedding.astype(float).tolist()))
        db.add(row)
        db.commit()
        db.refresh(row)
        return row


face_service = FaceService()
