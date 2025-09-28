# In src/events/event_types.py

from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from .. import models

class BaseEvent(BaseModel):
    """The base structure for all events in the system."""
    contact: models.Contact
    db_session: Any
    analysis: Dict[str, Any] # All events will carry the AI's analysis
    final_reply: Optional[str] = None
    stop_processing: bool = False
    stop_reason: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        arbitrary_types_allowed = True

# --- Specific Event Types ---

class InquiryEvent(BaseEvent):
    """For simple questions and answers."""
    pass

class GreetingEvent(BaseEvent):
    """For handling initial greetings to new or returning customers."""
    pass

class NameCaptureEvent(BaseEvent):
    """When the user provides their name."""
    pass

class BookingConfirmationRequestEvent(BaseEvent):
    """When the AI has all booking info and needs to ask the user for final confirmation."""
    pass

class BookingCreationEvent(BaseEvent):
    """When the user has confirmed and the system needs to create the booking."""
    stop_processing: bool = False
    stop_reason: Optional[str] = None

class BookingAbandonedEvent(BaseEvent):
    """When a user hesitates after being asked to confirm a booking."""
    pass

class HandoffEvent(BaseEvent):
    """When the conversation needs to be escalated to a human."""
    pass

"""
class BookingRescheduleEvent(BaseEvent):
    stop_processing: bool = False
    stop_reason: Optional[str] = None

class BookingEditServiceEvent(BaseEvent):
    stop_processing: bool = False
    stop_reason: Optional[str] = None
"""
class BookingUpdateEvent(BaseEvent):
    """Base class for booking updates like rescheduling or service edits."""
    stop_processing: bool = False
    stop_reason: Optional[str] = None