# src/routers/knowledge_router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..schemas import knowledge_schemas 
from ..crud import crud_knowledge, crud_ai_tagging
from ..database import SessionLocal

router = APIRouter(
    prefix="/api",
    tags=["Business Knowledge & Operations"] # A more descriptive tag
)

# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Knowledge Endpoints ---
@router.post("/knowledge/", response_model=knowledge_schemas.BusinessKnowledge)
def create_knowledge(item: knowledge_schemas.BusinessKnowledgeCreate, db: Session = Depends(get_db)):
    db_item = crud_knowledge.get_knowledge_item_by_type_and_key(db, item_type=item.type, item_key=item.key)
    if db_item:
        raise HTTPException(status_code=400, detail="Item with this key already exists.")
    return crud_knowledge.create_knowledge_item(db=db, item=item)

@router.get("/knowledge/", response_model=List[knowledge_schemas.BusinessKnowledge])
def read_knowledge(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud_knowledge.get_knowledge_items(db, skip=skip, limit=limit)

# Staff Endpoints
@router.post("/staff/", response_model=knowledge_schemas.StaffRoster, tags=["Staff Roster"])
def create_staff(member: knowledge_schemas.StaffRosterCreate, db: Session = Depends(get_db)):
    return crud_knowledge.create_staff_member(db=db, member=member)

@router.get("/staff/", response_model=List[knowledge_schemas.StaffRoster], tags=["Staff Roster"])
def read_staff(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud_knowledge.get_staff_members(db, skip=skip, limit=limit)

@router.post("/hours/", response_model=List[knowledge_schemas.BusinessHours], tags=["Business Hours"])
def update_hours(hours_update: knowledge_schemas.BusinessHoursUpdate, db: Session = Depends(get_db)):
    return crud_knowledge.bulk_update_business_hours(db=db, hours_update=hours_update)

@router.get("/hours/", response_model=List[knowledge_schemas.BusinessHours], tags=["Business Hours"])
def read_hours(db: Session = Depends(get_db)):
    return crud_knowledge.get_business_hours(db)

@router.post("/knowledge/bulk-upload", tags=["Business Knowledge"])
def create_knowledge_bulk(items: List[knowledge_schemas.BusinessKnowledgeCreate], db: Session = Depends(get_db)):
    """
    Handles bulk creation of knowledge items.
    It now intelligently handles different types (MENU, QA) based on the payload.
    """
    # Basic validation: ensure all items in a single upload are of the same type.
    if not items:
        raise HTTPException(status_code=400, detail="No items provided for upload.")
    
    item_type = items[0].type
    if not all(item.type == item_type for item in items):
        raise HTTPException(status_code=400, detail="All items in a bulk upload must be of the same type.")

    if item_type not in ['MENU', 'QA']:
        raise HTTPException(status_code=400, detail=f"Bulk upload for type '{item_type}' is not supported.")

    # We can reuse the existing crud function as it's already flexible enough.
    count = crud_knowledge.bulk_create_knowledge_items(db=db, items=items)
    
    print(f"✅ Successfully bulk-inserted {count} items of type '{item_type}'.")
    return {"status": "success", "items_created": count}

