from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models import Product, User, UserProductInterest
from backend.app.schemas import EnrollFaceResponse, InterestOut, OfferOut, UserCreate, UserOut
from backend.app.services.discounts import list_user_offers

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    if payload.email:
        existing = db.query(User).filter(User.email == payload.email).first()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        name=payload.name,
        email=payload.email,
        is_rewards_member=payload.is_rewards_member,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)) -> list[User]:
    return db.query(User).order_by(User.id).all()


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/{user_id}/enroll-face", response_model=EnrollFaceResponse)
def enroll_face(user_id: int, camera_index: int = 0, db: Session = Depends(get_db)) -> EnrollFaceResponse:
    """Opens the server-side webcam to capture and store a face embedding."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        from backend.cv.webcam_enroll import enroll_from_webcam

        embedding, samples = enroll_from_webcam(db, user_id, camera_index=camera_index)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EnrollFaceResponse(
        user_id=user_id,
        samples_captured=samples,
        embedding_dim=int(embedding.shape[0]),
        message="Face enrolled for rewards identification",
    )


@router.get("/{user_id}/interests", response_model=list[InterestOut])
def get_interests(user_id: int, db: Session = Depends(get_db)) -> list[InterestOut]:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    rows = (
        db.query(UserProductInterest, Product)
        .join(Product, Product.id == UserProductInterest.product_id)
        .filter(UserProductInterest.user_id == user_id)
        .order_by(UserProductInterest.weight.desc())
        .all()
    )
    return [
        InterestOut(
            product_id=interest.product_id,
            weight=interest.weight,
            updated_at=interest.updated_at,
            product_name=product.name,
        )
        for interest, product in rows
    ]


@router.get("/{user_id}/offers", response_model=list[OfferOut])
def get_offers(user_id: int, db: Session = Depends(get_db)) -> list[OfferOut]:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return list_user_offers(db, user_id)
