# src/crud/crud_menu.py
from sqlalchemy.orm import Session
from typing import List, Optional

from ..schemas import menu_schemas
from .. import models

# --- Menu Item CRUD ---
def get_menu_items(db: Session):
    return db.query(models.MenuItem).all()

def upsert_menu_item(db: Session, item: menu_schemas.MenuItemCreate) -> models.MenuItem:
    """
    Creates a new menu item or updates it if one with the same name already exists.
    """
    existing_item = db.query(models.MenuItem).filter(models.MenuItem.name == item.name).first()
    
    if existing_item:
        print(f"   - Updating existing menu item: '{item.name}'")
        existing_item.category = item.category
        existing_item.price = item.price
        existing_item.description = item.description
        db_item = existing_item
    else:
        print(f"   - Creating new menu item: '{item.name}'")
        db_item = models.MenuItem(**item.dict())
        db.add(db_item)
        
    db.commit()
    db.refresh(db_item)
    return db_item

def create_menu_item(db: Session, item: menu_schemas.MenuItemCreate):
    return upsert_menu_item(db, item) 

def bulk_create_menu_items(db: Session, items: List[menu_schemas.MenuItemCreate]) -> List[models.MenuItem]:
    """
    Handles bulk creation/update of menu items in a highly efficient manner.
    It performs one large query and one large commit, minimizing database round-trips.
    """
    processed_items = []
    item_names_in_upload = {item.name for item in items} # Use a set for faster lookups

    # 1. Fetch all potentially existing items in ONE single database query.
    existing_items_map = {
        item.name: item for item in db.query(models.MenuItem).filter(models.MenuItem.name.in_(item_names_in_upload)).all()
    }

    new_items_to_add = []
    for item_schema in items:
        existing_item = existing_items_map.get(item_schema.name)

        if existing_item:
            # UPDATE LOGIC: Modify the existing SQLAlchemy object in the session.
            existing_item.category = item_schema.category
            existing_item.price = item_schema.price
            existing_item.description = item_schema.description
            processed_items.append(existing_item)
        else:
            # CREATE LOGIC: Create a new object but DO NOT commit yet.
            new_item = models.MenuItem(**item_schema.dict())
            new_items_to_add.append(new_item)
            processed_items.append(new_item)
    
    # 2. Add all new items to the session in one go.
    if new_items_to_add:
        db.add_all(new_items_to_add)

    # 3. Commit all changes (updates and inserts) in ONE single transaction.
    db.commit()

    # 4. Refresh all processed objects to get their final state from the DB.
    for item in processed_items:
        db.refresh(item)
        
    return processed_items

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

def update_menu_item(db: Session, item_id: int, item_update: menu_schemas.MenuItemUpdate) -> Optional[models.MenuItem]:
    """
    Updates an existing menu item with new data.
    Only updates the fields that are provided in the payload.
    """
    db_item = db.query(models.MenuItem).filter(models.MenuItem.id == item_id).first()
    if not db_item:
        return None
    
    # Use Pydantic's .dict() with exclude_unset=True to get only the fields
    # that were actually sent in the request body.
    update_data = item_update.dict(exclude_unset=True)
    
    for key, value in update_data.items():
        setattr(db_item, key, value)
        
    db.commit()
    db.refresh(db_item)
    return db_item