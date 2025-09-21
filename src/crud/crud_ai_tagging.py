# src/crud/crud_ai_tagging.py

# from sqlalchemy.orm import Session
# from typing import List
# from .. import models
# from ..schemas import ai_tagging_schemas

# def get_ai_tag_rule(db: Session, rule_id: int) -> models.AIInterestTag:
#     """Fetches a single AI tagging rule by its ID."""
#     return db.query(models.AIInterestTag).filter(models.AIInterestTag.id == rule_id).first()

# def get_ai_tag_rules(db: Session, skip: int = 0, limit: int = 100) -> List[models.AIInterestTag]:
#     """Fetches all AI tagging rules."""
#     return db.query(models.AIInterestTag).offset(skip).limit(limit).all()

# def create_ai_tag_rule(db: Session, rule: ai_tagging_schemas.AIInterestTagCreate) -> models.AIInterestTag:
#     """Creates a new AI tagging rule."""
#     db_rule = models.AIInterestTag(keyword=rule.keyword, tag_to_apply=rule.tag_to_apply)
#     db.add(db_rule)
#     db.commit()
#     db.refresh(db_rule)
#     return db_rule

# def delete_ai_tag_rule(db: Session, rule_id: int) -> models.AIInterestTag:
#     """Deletes an AI tagging rule by its ID."""
#     db_rule = get_ai_tag_rule(db, rule_id)
#     if db_rule:
#         db.delete(db_rule)
#         db.commit()
#     return db_rule