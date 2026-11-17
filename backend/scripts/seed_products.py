"""Seed demo products, shelf zones, and member discounts."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python backend/scripts/seed_products.py` from repo root.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db import SessionLocal, init_db
from backend.app.models import Discount, DiscountScope, Product, ProductZone

CAMERA_ID = "webcam-0"

# Coordinates assume a ~1280x720 webcam preview; zones are screen regions.
PRODUCTS = [
    {
        "sku": "CRL-CHEER-12",
        "name": "Cheerios 12oz",
        "brand": "General Mills",
        "category": "cereal",
        "price": 4.99,
        "competitor_group": "cereal-oat",
        "zone": (40, 80, 300, 320),
    },
    {
        "sku": "CRL-FROST-12",
        "name": "Frosted Flakes 12oz",
        "brand": "Kellogg's",
        "category": "cereal",
        "price": 4.79,
        "competitor_group": "cereal-oat",
        "zone": (340, 80, 600, 320),
    },
    {
        "sku": "SNK-LAYS-CL",
        "name": "Lay's Classic",
        "brand": "Frito-Lay",
        "category": "snacks",
        "price": 3.49,
        "competitor_group": "chips-classic",
        "zone": (640, 80, 900, 320),
    },
    {
        "sku": "SNK-RUFF-CL",
        "name": "Ruffles Original",
        "brand": "Frito-Lay",
        "category": "snacks",
        "price": 3.69,
        "competitor_group": "chips-classic",
        "zone": (940, 80, 1200, 320),
    },
    {
        "sku": "BEV-COKE-12",
        "name": "Coca-Cola 12pk",
        "brand": "Coca-Cola",
        "category": "beverages",
        "price": 7.99,
        "competitor_group": "cola-12pk",
        "zone": (40, 360, 300, 620),
    },
    {
        "sku": "BEV-PEP-12",
        "name": "Pepsi 12pk",
        "brand": "Pepsi",
        "category": "beverages",
        "price": 7.49,
        "competitor_group": "cola-12pk",
        "zone": (340, 360, 600, 620),
    },
]


def seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        created = 0
        for item in PRODUCTS:
            product = db.query(Product).filter(Product.sku == item["sku"]).first()
            if not product:
                product = Product(
                    sku=item["sku"],
                    name=item["name"],
                    brand=item["brand"],
                    category=item["category"],
                    price=item["price"],
                    competitor_group=item["competitor_group"],
                )
                db.add(product)
                db.flush()
                created += 1

            x1, y1, x2, y2 = item["zone"]
            zone = (
                db.query(ProductZone)
                .filter(
                    ProductZone.camera_id == CAMERA_ID,
                    ProductZone.product_id == product.id,
                )
                .first()
            )
            if not zone:
                db.add(
                    ProductZone(
                        product_id=product.id,
                        camera_id=CAMERA_ID,
                        x1=x1,
                        y1=y1,
                        x2=x2,
                        y2=y2,
                        label=item["name"],
                    )
                )

            # Member general discount on every seeded product.
            existing_general = (
                db.query(Discount)
                .filter(
                    Discount.product_id == product.id,
                    Discount.scope == DiscountScope.MEMBER_GENERAL.value,
                )
                .first()
            )
            if not existing_general:
                db.add(
                    Discount(
                        product_id=product.id,
                        percent_off=5.0,
                        scope=DiscountScope.MEMBER_GENERAL.value,
                        min_interest_weight=0.0,
                        active=True,
                        title="Rewards member 5% off",
                    )
                )

            # Stronger personalized template.
            existing_pers = (
                db.query(Discount)
                .filter(
                    Discount.product_id == product.id,
                    Discount.scope == DiscountScope.PERSONALIZED.value,
                )
                .first()
            )
            if not existing_pers:
                db.add(
                    Discount(
                        product_id=product.id,
                        percent_off=15.0,
                        scope=DiscountScope.PERSONALIZED.value,
                        min_interest_weight=15.0,
                        active=True,
                        title="Interest-based offer",
                    )
                )

            existing_comp = (
                db.query(Discount)
                .filter(
                    Discount.product_id == product.id,
                    Discount.scope == DiscountScope.COMPETITOR.value,
                )
                .first()
            )
            if not existing_comp:
                db.add(
                    Discount(
                        product_id=product.id,
                        percent_off=10.0,
                        scope=DiscountScope.COMPETITOR.value,
                        min_interest_weight=0.0,
                        active=True,
                        title="Try our brand instead",
                    )
                )

        db.commit()
        total = db.query(Product).count()
        zones = db.query(ProductZone).filter(ProductZone.camera_id == CAMERA_ID).count()
        print(f"Seed complete. products={total} (new={created}) zones={zones} camera={CAMERA_ID}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
