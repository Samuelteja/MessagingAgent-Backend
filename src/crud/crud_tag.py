# src/crud.py
import random
import re
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, cast, Date, case
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from .. import models
from . import crud_contact
from ..schemas import tag_schemas

# ==============================================================================
# --- Tag CRUD Functions ---
# ==============================================================================

def get_tag_by_name(db: Session, name: str):
    return db.query(models.Tag).filter(models.Tag.name == name).first()

def get_tags(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Tag).offset(skip).limit(limit).all()

def create_tag(db: Session, tag: tag_schemas.TagCreate):
    db_tag = models.Tag(name=tag.name)
    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)
    return db_tag

def update_tags_for_contact(db: Session, contact_id: str, tag_names: List[str]) -> models.Contact:
    """
    Updates the tags for a single Contact, not a conversation.
    This is much more efficient.
    """
    # First, find the contact.
    contact = crud_contact.get_contact_by_contact_id(db, contact_id=contact_id)
    if not contact:
        return None
    
    # Find all the Tag objects that match the provided names.
    tags_to_assign = []
    if tag_names:
        tags_to_assign = db.query(models.Tag).filter(models.Tag.name.in_(tag_names)).all()
    
    # Directly assign the new list of tags to the contact's relationship.
    # SQLAlchemy's relationship magic handles the association table updates.
    contact.tags = tags_to_assign
    
    db.commit()
    db.refresh(contact)
    
    print(f"CRUD: Successfully updated tags for contact {contact_id} with: {[t.name for t in contact.tags]}")
    return contact
