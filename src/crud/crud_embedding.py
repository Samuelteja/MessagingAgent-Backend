# src/crud/crud_embedding.py

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import List
from .. import models
from ..services import embedding_service

def generate_and_save_embeddings_for_menu_items(db: Session, menu_items: List[models.MenuItem]):
    """
    Generates and saves embeddings for a list of menu items that don't have them yet.
    """
    print(f"   - Indexing {len(menu_items)} menu item(s)...")
    items_changed = False
    for item in menu_items:
        if item.embedding is None: # Only process items that need indexing
            text_to_embed = f"Service: {item.name}. Category: {item.category}. Description: {item.description}"
            print(f"      -> Preparing to embed text: '{text_to_embed[:70]}...'")
            vector = embedding_service.get_embedding(text_to_embed)
            if vector:
                items_changed = True
                item.embedding = vector
                flag_modified(item, "embedding")
                # ------------------------------

                print(f"      -> Generated embedding for '{item.name}' and flagged for saving.")

    if items_changed:
        print("      -> Committing new embeddings to the database...")
        db.commit()
    else:
        print("      -> No new embeddings were generated, no commit needed.")


def generate_and_save_embeddings_for_qas(db: Session, qa_items: List[models.BusinessKnowledge]):
    """
    Generates and saves embeddings for a list of Q&A items that don't have them yet.
    """
    print(f"   - Indexing {len(qa_items)} Q&A item(s)...")
    items_changed = False
    for item in qa_items:
        if item.embedding is None:
            text_to_embed = f"Question: {item.key}. Answer: {item.value}"
            vector = embedding_service.get_embedding(text_to_embed)
            if vector:
                items_changed = True
                item.embedding = vector
                flag_modified(item, "embedding") # <-- ADD THE FIX HERE TOO
                print(f"      -> Generated embedding for Q: '{item.key}' and flagged for saving.")
    
    if items_changed:
        print("      -> Committing new embeddings to the database...")
        db.commit()