# src/crud/crud_tag.py
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
    if not contact or not tag_names:
        return contact
    
    existing_tag_names = {tag.name for tag in contact.tags}

    new_tags_to_add_names = [name for name in tag_names if name not in existing_tag_names]

    if not new_tags_to_add_names:
        print(f"CRUD: No new tags to add for contact {contact_id}. All suggested tags already exist.")
        return contact
        
    print(f"CRUD: Contact already has tags: {existing_tag_names}. Adding new tags: {new_tags_to_add_names}")

    for tag_name in new_tags_to_add_names:
        tag = get_tag_by_name(db, name=tag_name)
        if not tag:
            # If the AI suggests a tag that doesn't exist, we create it on the fly.
            print(f"   -> Tag '{tag_name}' not found. Creating it now.")
            tag = create_tag(db, tag_schemas.TagCreate(name=tag_name))
        
        # Append the persistent Tag object to the contact's relationship.
        contact.tags.append(tag)
    
    final_tags_in_session = [t.name for t in contact.tags]
    print(f"CRUD: Staged tag updates for contact {contact_id}. Session now contains tags: {final_tags_in_session}")
    return contact