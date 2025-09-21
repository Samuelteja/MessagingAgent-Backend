# src/routers/menu_router.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from ..schemas import menu_schemas
from ..database import SessionLocal
from ..services import ai_service
from ..crud import crud_tag_rules, crud_menu
from .. import models

router = APIRouter(prefix="/api/menu", tags=["Menu & Upsells"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _run_ai_tag_generation(db: Session, menu_items_to_process: List[models.MenuItem]):
    """
    This is the function that will be executed in the background.
    It now ONLY processes the specific items passed to it.
    """
    print(f"🤖 Background Task: Starting AI Tag Generation for {len(menu_items_to_process)} new item(s)...")
    if not menu_items_to_process:
        print("   - No new menu items to analyze. Skipping.")
        return

    try:
        generated_rules = ai_service.generate_tagging_rules_from_menu(menu_items_to_process)
        for rule_suggestion in generated_rules:
            crud_tag_rules.create_or_update_tag_rule_from_suggestion(db, rule_suggestion)
        
        print(f"✅ Background Task: Finished processing {len(generated_rules)} AI suggestions.")
    except Exception as e:
        print(f"❌ Background Task Error: Failed to generate AI tags. Error: {e}")



@router.get("/", response_model=List[menu_schemas.MenuItem])
def read_menu_items(db: Session = Depends(get_db)):
    return crud_menu.get_menu_items(db)

@router.post("/", response_model=menu_schemas.MenuItem)
def create_new_menu_item(
    item: menu_schemas.MenuItemCreate, 
    background_tasks: BackgroundTasks, # <-- ADD THIS DEPENDENCY
    db: Session = Depends(get_db)
):
    db_item = crud_menu.create_menu_item(db, item)
    background_tasks.add_task(_run_ai_tag_generation, db, [db_item])
    return db_item

@router.post("/bulk-upload", tags=["Menu & Upsells"])
def create_menu_items_bulk(
    items: List[menu_schemas.MenuItemCreate], 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    try:
        new_items = crud_menu.bulk_create_menu_items(db=db, items=items)
        # Also trigger the background task here
        background_tasks.add_task(_run_ai_tag_generation, db, new_items)
        return {"status": "success", "items_created": len(new_items)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An error occurred: {e}")

@router.post("/{item_id}/upsell", response_model=menu_schemas.UpsellRule)
def set_upsell_rule(item_id: int, rule: menu_schemas.UpsellRuleCreate, db: Session = Depends(get_db)):
    db_rule = crud_menu.create_or_update_upsell_rule(db, trigger_item_id=item_id, rule=rule)
    if not db_rule:
        raise HTTPException(status_code=404, detail="Trigger menu item not found")
    return db_rule