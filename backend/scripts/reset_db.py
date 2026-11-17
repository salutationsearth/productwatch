"""Wipe local SQLite data and reseed products/zones/discounts.

Usage (from repo root, stop uvicorn first if the DB is locked):

    python backend/scripts/reset_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from backend.app.config import settings
from backend.app.db import engine, init_db
from backend.app import models  # noqa: F401
from backend.scripts.seed_products import seed


def _clear_outbox() -> int:
    outbox = settings.outbox_dir
    if not outbox.exists():
        return 0
    n = 0
    for path in outbox.glob("*"):
        if path.is_file():
            path.unlink()
            n += 1
    return n


def wipe() -> None:
    init_db()
    # Child → parent order so SQLite FK checks stay happy.
    tables = [
        "marketing_emails",
        "agent_run_logs",
        "user_offers",
        "interest_events",
        "user_product_interest",
        "face_embeddings",
        "product_zones",
        "discounts",
        "products",
        "users",
    ]
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        for name in tables:
            conn.execute(text(f"DELETE FROM {name}"))
        # Reset autoincrement counters
        conn.execute(text("DELETE FROM sqlite_sequence"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
    cleared = _clear_outbox()
    print(f"Wiped tables: {', '.join(tables)}")
    print(f"Cleared {cleared} outbox file(s)")


def main() -> None:
    wipe()
    seed()
    print("Database reset complete — products/zones/discounts reseeded.")


if __name__ == "__main__":
    main()
