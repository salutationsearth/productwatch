from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models import Product, User, UserProductInterest
from backend.app.schemas import EnrollFaceResponse, InterestOut, OfferOut, UserCreate, UserOut
from backend.app.services.discounts import list_user_offers
from backend.app.services.face import face_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        name=payload.name,
        email=str(payload.email),
        is_rewards_member=payload.is_rewards_member,
        face_enrolled=False,
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


@router.post("/{user_id}/enroll-face-frames", response_model=EnrollFaceResponse)
async def enroll_face_frames(
    user_id: int,
    frames: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> EnrollFaceResponse:
    """Browser webcam enrollment: accept JPEG/PNG frames, average embeddings, store.
    Server never opens a camera — frames come from the browser.
    """
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not frames:
        raise HTTPException(status_code=400, detail="No frames uploaded")
    blobs: list[bytes] = []
    for f in frames[:24]:
        blobs.append(await f.read())
    try:
        embedding, samples = face_service.enroll_from_image_bytes(db, user_id, blobs)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.refresh(user)
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
            first_seen_at=interest.first_seen_at,
            last_seen_at=interest.last_seen_at,
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
