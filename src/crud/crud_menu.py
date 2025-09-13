# src/menu_crud.py
from sqlalchemy.orm import Session
from typing import List

from ..schemas import menu_schemas
from .. import models

# --- Menu Item CRUD ---
def get_menu_items(db: Session):
    return db.query(models.MenuItem).all()

def create_menu_item(db: Session, item: menu_schemas.MenuItemCreate):
    db_item = models.MenuItem(**item.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

def bulk_create_menu_items(db: Session, items: List[menu_schemas.MenuItemCreate]):
    """
    Creates multiple MenuItem objects in the database from a list of schemas.
    """
    db_items = [models.MenuItem(**item.dict()) for item in items]
    db.bulk_save_objects(db_items)
    db.commit()
    return len(db_items)

# --- Upsell Rule CRUD ---
def create_or_update_upsell_rule(db: Session, trigger_item_id: int, rule: menu_schemas.UpsellRuleCreate):
    # Find the trigger menu item
    trigger_item = db.query(models.MenuItem).filter(models.MenuItem.id == trigger_item_id).first()
    if not trigger_item:
        return None
    
    # If a rule already exists, update it. Otherwise, create a new one.
    if trigger_item.upsell_rule:
        trigger_item.upsell_rule.suggestion_text = rule.suggestion_text
        trigger_item.upsell_rule.upsell_menu_item_id = rule.upsell_menu_item_id
    else:
        new_rule = models.UpsellRule(**rule.dict(), trigger_menu_item_id=trigger_item_id)
        db.add(new_rule)
    
    db.commit()
    db.refresh(trigger_item)
    return trigger_item.upsell_rule