"""Capture webcam frames and average face embeddings for enrollment."""

from __future__ import annotations

import time

import cv2
import numpy as np
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.services.face import face_service


def enroll_from_webcam(
    db: Session,
    user_id: int,
    sample_count: int | None = None,
    camera_index: int = 0,
    timeout_seconds: float = 45.0,
) -> tuple[np.ndarray, int]:
    """
    Open the webcam, collect face embeddings, average them, persist to DB.
    Press Q to cancel. Returns (embedding, samples_used).
    """
    sample_count = sample_count or settings.enroll_sample_count
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open webcam index {camera_index}")

    embeddings: list[np.ndarray] = []
    started = time.time()
    last_capture = 0.0

    try:
        while len(embeddings) < sample_count and (time.time() - started) < timeout_seconds:
            ok, frame = cap.read()
            if not ok:
                continue
            display = frame.copy()
            face = face_service.largest_face(frame)
            if face is not None:
                x, y, w, h = map(int, face[:4])
                cv2.rectangle(display, (x, y), (x + w, y + h), (40, 200, 80), 2)
                if time.time() - last_capture > 0.25:
                    emb = face_service.embed_face(frame, face)
                    embeddings.append(emb)
                    last_capture = time.time()

            cv2.putText(
                display,
                f"Enrolling user {user_id}: {len(embeddings)}/{sample_count}",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
            )
            cv2.putText(
                display,
                "Look at the camera. Press Q to cancel.",
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (200, 200, 200),
                1,
            )
            cv2.imshow("ProductWatch — Face Enrollment", display)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()

    if len(embeddings) < max(3, sample_count // 3):
        raise RuntimeError(
            f"Not enough face samples captured ({len(embeddings)}). Try better lighting."
        )

    avg = np.mean(np.stack(embeddings, axis=0), axis=0)
    avg = avg / (np.linalg.norm(avg) + 1e-8)
    face_service.save_embedding(db, user_id, avg)
    return avg, len(embeddings)


def enroll_user_cli(user_id: int, camera_index: int = 0) -> None:
    from backend.app.db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        emb, n = enroll_from_webcam(db, user_id, camera_index=camera_index)
        print(f"Enrolled user {user_id} with {n} samples, dim={emb.shape[0]}")
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Enroll a user face via webcam")
    parser.add_argument("user_id", type=int)
    parser.add_argument("--camera", type=int, default=0)
    args = parser.parse_args()
    enroll_user_cli(args.user_id, camera_index=args.camera)
