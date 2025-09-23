# src/services/embedding_service.py

import os
from dotenv import load_dotenv
import google.generativeai as genai
from typing import List

# Load environment variables to get the API key
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in .env file")
genai.configure(api_key=GOOGLE_API_KEY)

EMBEDDING_MODEL = "text-embedding-004"

def get_embedding(text: str) -> List[float]:
    """
    Calls the Google AI Embedding API to convert a string of text into a vector.
    """
    try:
        # The embed_content function is highly optimized for this task.
        result = genai.embed_content(
            model=f"models/{EMBEDDING_MODEL}",
            content=text,
            task_type="RETRIEVAL_QUERY" # Use 'RETRIEVAL_DOCUMENT' for the items being stored
        )
        return result['embedding']
    except Exception as e:
        print(f"❌ Error generating embedding for text: '{text[:50]}...'. Error: {e}")
        return []