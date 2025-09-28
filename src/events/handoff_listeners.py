# In src/events/handoff_listeners.py

from .event_types import HandoffEvent
from ..crud import crud_contact

def pause_ai_for_contact(event: HandoffEvent):
    """LISTENER: Pauses the AI for the contact for a long duration."""
    print("  [Listener]: Running pause_ai_for_contact...")
    crud_contact.set_ai_pause(db=event.db_session, contact_id=event.contact.contact_id)