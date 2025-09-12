# src/schemas.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import time, datetime

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

# --- Tag Schemas ---
class TagBase(BaseModel):
    name: str

class TagCreate(TagBase):
    pass

class Tag(TagBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

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
    tags: List[Tag] = [] # This will hold the list of related tags

    model_config = ConfigDict(from_attributes=True)

# --- Business Knowledge Schemas ---
class BusinessKnowledgeBase(BaseModel):
    type: str
    key: str
    value: str

class BusinessKnowledgeCreate(BusinessKnowledgeBase):
    pass

class BusinessKnowledge(BusinessKnowledgeBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# --- Staff Roster Schemas ---
class StaffRosterBase(BaseModel):
    name: str
    specialties: str
    schedule: Dict[str, Any] # e.g., {"Monday": "10:00-18:00"}

class StaffRosterCreate(StaffRosterBase):
    pass

class StaffRoster(StaffRosterBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# --- Business Hours Schemas ---
class BusinessHoursBase(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6) # 0=Monday, 6=Sunday
    open_time: Optional[time]
    close_time: Optional[time]
    quiet_hours_start: Optional[time]
    quiet_hours_end: Optional[time]

class BusinessHoursUpdate(BaseModel):
    # We will receive a list of hours for the whole week to update at once
    hours: List[BusinessHoursBase]

class BusinessHours(BusinessHoursBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

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

class TagsUpdate(BaseModel):
    tags: List[str]

class NormalizedMessage(BaseModel):
    """A standardized message object that the controller will use, regardless of the source."""
    channel: str
    contact_id: str
    pushname: Optional[str] = "Customer" # A safe default
    body: str