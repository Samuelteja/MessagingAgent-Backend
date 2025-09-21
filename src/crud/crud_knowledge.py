# src/crud/crud_knowledge.py
import random
import re
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, cast, Date, case
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from .. import models
from ..schemas import analytics_schemas, campaign_schemas, contact_schemas, knowledge_schemas, tag_schemas, webhook_schemas

# ==============================================================================
# --- Business Knowledge & Staff CRUD Functions ---
# ==============================================================================

def get_knowledge_item_by_type_and_key(db: Session, item_type: str, item_key: str):
    return db.query(models.BusinessKnowledge).filter(
        models.BusinessKnowledge.type == item_type,
        models.BusinessKnowledge.key == item_key
    ).first()

def get_knowledge_items(db: Session, skip: int = 0, limit: int = 200):
    return db.query(models.BusinessKnowledge).offset(skip).limit(limit).all()

def create_knowledge_item(db: Session, item: knowledge_schemas.BusinessKnowledgeCreate):
    db_item = models.BusinessKnowledge(**item.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

def bulk_create_knowledge_items(db: Session, items: List[knowledge_schemas.BusinessKnowledgeCreate]):
    db_items = [models.BusinessKnowledge(**item.dict()) for item in items]
    db.bulk_save_objects(db_items)
    db.commit()
    return len(db_items)

def get_staff_members(db: Session, skip: int = 0, limit: int = 50):
    return db.query(models.StaffRoster).offset(skip).limit(limit).all()

def create_staff_member(db: Session, member: knowledge_schemas.StaffRosterCreate):
    db_member = models.StaffRoster(**member.dict())
    db.add(db_member)
    db.commit()
    db.refresh(db_member)
    return db_member

# ==============================================================================
# --- Business Hours & Analytics CRUD Functions --
# ==============================================================================

def get_business_hours(db: Session):
    return db.query(models.BusinessHours).order_by(models.BusinessHours.day_of_week).all()

def bulk_update_business_hours(db: Session, hours_update: knowledge_schemas.BusinessHoursUpdate):
    db.query(models.BusinessHours).delete()
    for hour_data in hours_update.hours:
        db_hour = models.BusinessHours(**hour_data.dict())
        db.add(db_hour)
    db.commit()
    return get_business_hours(db)