# src/routers/tag_router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..schemas import tag_schemas, tag_rule_schemas
from ..crud import crud_tag, crud_tag_rules, crud_menu
from ..database import SessionLocal

router = APIRouter(
    prefix="/api",
    tags=["Tags"]
)

# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/tags/", response_model=tag_schemas.Tag, summary="Create a New Tag")
def create_new_tag(tag: tag_schemas.TagCreate, db: Session = Depends(get_db)):
    db_tag = crud_tag.get_tag_by_name(db, name=tag.name)
    if db_tag:
        raise HTTPException(status_code=400, detail="Tag with this name already exists")
    return crud_tag.create_tag(db=db, tag=tag)

@router.get("/tags/", response_model=List[tag_schemas.Tag], summary="Get All Tags")
def read_tags(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud_tag.get_tags(db, skip=skip, limit=limit)


@router.get("/tag-rules/", response_model=List[tag_rule_schemas.TagRule])
def read_all_tag_rules(db: Session = Depends(get_db)):
    """
    Retrieves all AI-generated keyword-to-tag rules for display in the dashboard.
    """
    return crud_tag_rules.get_tag_rules(db)

@router.delete("/tag-rules/{rule_id}", response_model=tag_rule_schemas.TagRule)
def delete_a_tag_rule(rule_id: int, db: Session = Depends(get_db)):
    """
    Allows the owner to delete a specific, unwanted AI-generated rule.
    """
    db_rule = crud_tag_rules.delete_tag_rule(db, rule_id=rule_id)
    if db_rule is None:
        raise HTTPException(status_code=404, detail="Tag rule not found")
    return db_rule