# src/crud/crud_tag_rules.py

from sqlalchemy.orm import Session, joinedload
from typing import Dict, List
from . import crud_tag
from .. import models
from ..schemas import tag_schemas

def create_or_update_tag_rule_from_suggestion(db: Session, rule_suggestion: Dict):
    """
    This is the core "smart" function. It takes a suggestion from the AI,
    ensures the tag exists, and then creates the rule if it doesn't already exist.

    Args:
        rule_suggestion (Dict): A dictionary like {"keyword": "bridal", "suggested_tag_name": "interest:bridal"}
    """
    keyword = rule_suggestion.get("keyword")
    suggested_tag_name = rule_suggestion.get("suggested_tag_name")

    if not keyword or not suggested_tag_name:
        return # Skip invalid suggestions

    # Step 1: Ensure the tag exists in the main 'tags' table.
    tag = crud_tag.get_tag_by_name(db, name=suggested_tag_name)
    if not tag:
        # If the tag doesn't exist, create it.
        print(f"   - Tag '{suggested_tag_name}' not found. Creating it...")
        tag = crud_tag.create_tag(db, tag_schemas.TagCreate(name=suggested_tag_name))

    # Step 2: Check if a rule for this keyword already exists.
    existing_rule = db.query(models.TagRule).filter(models.TagRule.keyword == keyword).first()

    if existing_rule:
        # Optional: We could update the rule to point to the new tag_id, but for now, skipping is safer.
        print(f"   - Rule for keyword '{keyword}' already exists. Skipping.")
        return
    else:
        # Step 3: If the rule doesn't exist, create it.
        print(f"   - Creating new rule: '{keyword}' -> '{suggested_tag_name}' (Tag ID: {tag.id})")
        new_rule = models.TagRule(keyword=keyword, tag_id=tag.id)
        db.add(new_rule)
        db.commit()

def get_tag_rules(db: Session, skip: int = 0, limit: int = 200) -> List[models.TagRule]:
    """
    Fetches all AI tagging rules, and eagerly loads the related 'tag' object
    to prevent extra database queries.
    """
    return (
        db.query(models.TagRule)
        .options(joinedload(models.TagRule.tag))
        .order_by(models.TagRule.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )

def delete_tag_rule(db: Session, rule_id: int) -> models.TagRule:
    """Deletes an AI tagging rule by its ID."""
    db_rule = db.query(models.TagRule).filter(models.TagRule.id == rule_id).first()
    if db_rule:
        db.delete(db_rule)
        db.commit()
    return db_rule