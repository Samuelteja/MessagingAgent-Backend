# src/schemas/webhook_schemas.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import time, datetime

# --- Webhook Schemas (Unchanged) ---
class Sender(BaseModel):
    pushname: Optional[str] = None

class WebhookPayload(BaseModel):
    event: str
    session: str
    body: Optional[str] = None
    from_number: Optional[str] = Field(None, alias='from')
    id: Optional[str] = None
    sender: Optional[Sender] = None

class NormalizedMessage(BaseModel):
    """A standardized message object that the controller will use, regardless of the source."""
    channel: str
    contact_id: str
    pushname: Optional[str] = "Customer" # A safe default
    body: str