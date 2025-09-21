# src/routers/profile_router.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..crud import crud_profile
from ..schemas import profile_schemas

router = APIRouter(
    prefix="/api/profile",
    tags=["Business Profile"]
)

# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=profile_schemas.Profile, summary="Get Business Profile")
def read_profile(db: Session = Depends(get_db)):
    """Retrieves the salon's current business profile."""
    return crud_profile.get_profile(db)

@router.put("/", response_model=profile_schemas.Profile, summary="Update Business Profile")
def update_business_profile(profile_data: profile_schemas.ProfileUpdate, db: Session = Depends(get_db)):
    """Updates the salon's name and description."""
    return crud_profile.update_profile(db, profile_data=profile_data)