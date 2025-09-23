# src/routers/knowledge_router.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from ..schemas import knowledge_schemas
from ..crud import crud_knowledge, crud_embedding
from ..database import SessionLocal
from .. import models

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

def _run_knowledge_post_processing(item_ids: List[int]): # <-- Accepts a list of IDs
    """
    This background task for knowledge items now creates its own DB session.
    """
    print(f"🤖 Background Task: Starting post-processing for {len(item_ids)} knowledge item(s)...")
    db = SessionLocal() # Create independent session
    try:
        knowledge_items = db.query(models.BusinessKnowledge).filter(models.BusinessKnowledge.id.in_(item_ids)).all()
        qa_items_to_index = [item for item in knowledge_items if item.type == 'QA']
        
        if qa_items_to_index:
            try:
                print(f"   - Step 1: Generating Embeddings for {len(qa_items_to_index)} new Q&A item(s)...")
                crud_embedding.generate_and_save_embeddings_for_qas(db, qa_items_to_index)
                print("   - ✅ Embedding indexing for Q&A items completed successfully.")
            except Exception as e:
                print(f"   - ❌ ERROR during Q&A Embedding Indexing step: {e}")
    finally:
        db.close() # Always close the session
        print("🤖 Background Task: Knowledge post-processing finished.")

@router.post("/knowledge/", response_model=knowledge_schemas.BusinessKnowledge)
def create_knowledge(
    item: knowledge_schemas.BusinessKnowledgeCreate, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    db_item = crud_knowledge.create_knowledge_item(db=db, item=item)
    background_tasks.add_task(_run_knowledge_post_processing, [db_item.id]) # Pass ID
    return db_item


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
def create_knowledge_bulk(items: List[knowledge_schemas.BusinessKnowledgeCreate], background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
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
    new_items = crud_knowledge.bulk_create_knowledge_items(db=db, items=items)
    new_item_ids = [item.id for item in new_items]
    background_tasks.add_task(_run_knowledge_post_processing, new_item_ids) # Pass IDs
    return {"status": "success", "items_created": len(new_items)}
