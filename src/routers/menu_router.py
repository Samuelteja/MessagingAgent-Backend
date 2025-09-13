# src/menu_router.py
from ..crud import crud_menu
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..schemas import menu_schemas
from ..database import SessionLocal

router = APIRouter(prefix="/api/menu", tags=["Menu & Upsells"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=List[menu_schemas.MenuItem])
def read_menu_items(db: Session = Depends(get_db)):
    return crud_menu.get_menu_items(db)

@router.post("/", response_model=menu_schemas.MenuItem)
def create_new_menu_item(item: menu_schemas.MenuItemCreate, db: Session = Depends(get_db)):
    return crud_menu.create_menu_item(db, item)

@router.post("/bulk-upload", tags=["Menu & Upsells"])
def create_menu_items_bulk(items: List[menu_schemas.MenuItemCreate], db: Session = Depends(get_db)):
    """
    Handles bulk creation of menu items from a parsed Excel file.
    """
    try:
        count = crud_menu.bulk_create_menu_items(db=db, items=items)
        return {"status": "success", "items_created": count}
    except Exception as e:
        # It's good practice to catch potential database errors
        raise HTTPException(status_code=400, detail=f"An error occurred during bulk insert: {e}")

@router.post("/{item_id}/upsell", response_model=menu_schemas.UpsellRule)
def set_upsell_rule(item_id: int, rule: menu_schemas.UpsellRuleCreate, db: Session = Depends(get_db)):
    db_rule = crud_menu.create_or_update_upsell_rule(db, trigger_item_id=item_id, rule=rule)
    if not db_rule:
        raise HTTPException(status_code=404, detail="Trigger menu item not found")
    return db_rule