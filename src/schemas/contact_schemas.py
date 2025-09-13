# src/schemas.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import time, datetime
from .tag_schemas import Tag

# --- Contact Schemas ---
class ContactBase(BaseModel):
    contact_id: str
    name: Optional[str] = None

class ContactCreate(ContactBase):
    pass

class Contact(ContactBase):
    id: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
    tags: List[Tag] = []

# --- Conversation Schemas ---
class Conversation(BaseModel):
    id: int
    channel: str
    contact: Contact
    incoming_text: str
    outgoing_text: Optional[str]
    status: str
    outcome: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)

class TagsUpdatePayload(BaseModel):
    tags: List[str]

class ManualReplyPayload(BaseModel):
    message: str = Field(..., min_length=1)

class ContactImport(BaseModel):
    """Defines the structure for a single contact in the import list."""
    contact_id: str = Field(..., example="919876543210@c.us")
    name: str = Field(..., example="Priya Kumar")

class ContactImportPayload(BaseModel):
    """Defines the structure for the entire payload, which is a list of contacts."""
    contacts: List[ContactImport]