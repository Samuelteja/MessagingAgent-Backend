# src/schemas/knowledge_schemas.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import time, datetime

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

class StaffDropdown(BaseModel):
    id: int
    name: str