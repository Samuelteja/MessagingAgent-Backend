from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..schemas import tag_schemas
from ..crud import crud_tag
from ..database import SessionLocal

router = APIRouter(
    prefix="/api/tags",
    tags=["Tags"]
)

# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/", response_model=tag_schemas.Tag, summary="Create a New Tag")
def create_new_tag(tag: tag_schemas.TagCreate, db: Session = Depends(get_db)):
    db_tag = crud_tag.get_tag_by_name(db, name=tag.name)
    if db_tag:
        raise HTTPException(status_code=400, detail="Tag with this name already exists")
    return crud_tag.create_tag(db=db, tag=tag)

@router.get("/", response_model=List[tag_schemas.Tag], summary="Get All Tags")
def read_tags(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud_tag.get_tags(db, skip=skip, limit=limit)