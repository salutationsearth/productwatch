"""Create demo interest timestamps and force one agent cycle (for dashboard demos)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db import SessionLocal, init_db
from backend.app.models import Product, User, UserProductInterest
from backend.app.services.marketing_agent import run_agent_once


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.face_enrolled.is_(True)).order_by(User.id.desc()).first()
        product = db.query(Product).first()
        if not user or not product:
            print("Need at least one face-enrolled user and one product. Sign up at /onboard first.")
            return
        now = datetime.now(timezone.utc)
        interest = (
            db.query(UserProductInterest)
            .filter(UserProductInterest.user_id == user.id, UserProductInterest.product_id == product.id)
            .first()
        )
        if not interest:
            interest = UserProductInterest(
                user_id=user.id,
                product_id=product.id,
                weight=25.0,
                first_seen_at=now - timedelta(hours=2),
                last_seen_at=now - timedelta(minutes=5),
            )
            db.add(interest)
        else:
            interest.weight = max(interest.weight, 25.0)
            interest.last_seen_at = now - timedelta(minutes=5)
        # Clear user cooldown for demo
        user.last_marketing_email_at = None
        db.commit()
        log = run_agent_once(db)
        print(log.summary)
        print("Open /dashboard and check backend/data/outbox for the email HTML.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
