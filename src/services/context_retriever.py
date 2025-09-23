# src/services/context_retriever.py

from sqlalchemy.orm import Session
from typing import List
import numpy as np
from ..crud import crud_menu, crud_knowledge
from . import embedding_service

def _cosine_similarity(v1, v2):
    """Helper function to calculate similarity between two vectors."""
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

def find_relevant_context(user_message: str, db: Session, top_k: int = 3) -> str:
    """
    This is the core RAG function. It finds the most relevant Menu and Q&A items
    based on semantic similarity to the user's message.
    """
    print("🤖 Retrieving relevant context using vector similarity search...")
    
    # 1. Get the vector for the user's query
    query_vector = embedding_service.get_embedding(user_message)
    if not query_vector:
        return "No relevant context found."

    # 2. Find relevant menu items
    all_menu_items = crud_menu.get_menu_items(db)
    menu_similarities = []
    for item in all_menu_items:
        if item.embedding:
            similarity = _cosine_similarity(query_vector, item.embedding)
            menu_similarities.append((similarity, item))

    # 3. Find relevant Q&A items
    all_knowledge_items = crud_knowledge.get_knowledge_items(db)
    qa_items = [item for item in all_knowledge_items if item.type == 'QA']
    qa_similarities = []
    for item in qa_items:
        if item.embedding:
            similarity = _cosine_similarity(query_vector, item.embedding)
            qa_similarities.append((similarity, item))
    
    # 4. Sort and get the top_k results from both lists
    menu_similarities.sort(key=lambda x: x[0], reverse=True)
    qa_similarities.sort(key=lambda x: x[0], reverse=True)
    
    top_items = menu_similarities[:top_k] + qa_similarities[:top_k]
    
    # 5. Format the retrieved context for the AI prompt
    context_parts = []
    if top_items:
        print(f"   - Found {len(top_items)} potentially relevant knowledge items.")
        context_parts.append("## Relevant Knowledge Base Snippets (Use this to answer the user):")
        for similarity, item in top_items:
            if hasattr(item, 'price'):
                context_parts.append(f"- Service: {item.name}, Price: {item.price}, Description: {item.description}")
            else: # It's a Q&A item
                context_parts.append(f"- Q: {item.key}, A: {item.value}")
    
    return "\n".join(context_parts)