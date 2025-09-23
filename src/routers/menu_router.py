# src/routers/menu_router.py

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List

# Correctly import all necessary modules
from .. import models
from ..database import SessionLocal
from ..services import ai_service
from ..crud import crud_menu, crud_tag_rules, crud_embedding
from ..schemas import menu_schemas

router = APIRouter(prefix="/api/menu", tags=["Menu & Upsells"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- THIS IS THE SINGLE, CORRECT, UNIFIED BACKGROUND TASK ---
def _run_menu_post_processing(item_ids: List[int]):
    """
    This single, robust background task creates its own DB session to handle
    all post-processing for new menu items (Tag Generation & Embedding).
    """
    print(f"🤖 Background Task: Starting post-processing for {len(item_ids)} menu item(s)...")
    db = SessionLocal() # Create a new, independent session
    try:
        menu_items = db.query(models.MenuItem).filter(models.MenuItem.id.in_(item_ids)).all()
        if not menu_items:
            return

        # Task 1: AI Smart Tag Generation
        try:
            print("   - Step 1: Generating AI Tagging Rules...")
            generated_rules = ai_service.generate_tagging_rules_from_menu(menu_items)
            for rule_suggestion in generated_rules:
                crud_tag_rules.create_or_update_tag_rule_from_suggestion(db, rule_suggestion)
            print("   - ✅ AI Tagging Rules generated successfully.")
        except Exception as e:
            print(f"   - ❌ ERROR during AI Tag Generation step: {e}")

        # Task 2: Embedding Indexing
        try:
            print("   - Step 2: Generating Embeddings...")
            crud_embedding.generate_and_save_embeddings_for_menu_items(db, menu_items)
            print("   - ✅ Embedding indexing completed successfully.")
        except Exception as e:
            print(f"   - ❌ ERROR during Embedding Indexing step: {e}")
    finally:
        db.close()
        print("🤖 Background Task: Post-processing finished and DB session closed.")


# --- ROUTER ENDPOINTS ---

@router.get("/", response_model=List[menu_schemas.MenuItem])
def read_menu_items(db: Session = Depends(get_db)):
    return crud_menu.get_menu_items(db)


@router.post("/", response_model=menu_schemas.MenuItem)
def create_new_menu_item(
    item: menu_schemas.MenuItemCreate, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    # This now correctly uses the efficient upsert logic
    db_item = crud_menu.upsert_menu_item(db, item)
    # The call to the background task is correct, passing the ID
    background_tasks.add_task(_run_menu_post_processing, [db_item.id])
    return db_item


@router.post("/bulk-upload", tags=["Menu & Upsells"])
def create_menu_items_bulk(
    items: List[menu_schemas.MenuItemCreate], 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    # This now correctly uses the high-performance bulk upsert logic
    new_items = crud_menu.bulk_create_menu_items(db=db, items=items)
    new_item_ids = [item.id for item in new_items]
    background_tasks.add_task(_run_menu_post_processing, new_item_ids)
    return {"status": "success", "items_created": len(new_items)}


@router.post("/{item_id}/upsell", response_model=menu_schemas.UpsellRule)
def set_upsell_rule(item_id: int, rule: menu_schemas.UpsellRuleCreate, db: Session = Depends(get_db)):
    db_rule = crud_menu.create_or_update_upsell_rule(db, trigger_item_id=item_id, rule=rule)
    if not db_rule:
        raise HTTPException(status_code=404, detail="Trigger menu item not found")
    return db_rule