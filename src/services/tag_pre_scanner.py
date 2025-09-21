# src/services/tag_pre_scanner.py

from sqlalchemy.orm import Session
from typing import List
from ..crud import crud_tag_rules

def find_relevant_tags(message_text: str, db: Session) -> List[str]:
    """
    Scans the user's message for keywords from the tag_rules table.
    This is a fast, efficient pre-processing step before calling the main AI.

    Args:
        message_text: The incoming text from the user.
        db: The database session.

    Returns:
        A list of tag names (e.g., ['interest:haircut', 'interest:bridal']) that are relevant.
    """
    print("🤖 Pre-scanning message for keywords...")
    
    # We can optimize this by caching these rules in a future sprint,
    # but for now, fetching them is fast enough.
    all_rules = crud_tag_rules.get_tag_rules(db, limit=1000) # Fetch all rules
    
    if not all_rules:
        return []

    # Normalize the user's message to lowercase for case-insensitive matching.
    normalized_message = message_text.lower()
    
    matched_tags = set() # Use a set to automatically handle duplicate tags

    for rule in all_rules:
        # Simple and fast substring check.
        if rule.keyword.lower() in normalized_message:
            matched_tags.add(rule.tag.name)
            print(f"   - Keyword match found: '{rule.keyword}' -> applying tag '{rule.tag.name}'")

    if not matched_tags:
        print("   - No keyword matches found.")

    return list(matched_tags)