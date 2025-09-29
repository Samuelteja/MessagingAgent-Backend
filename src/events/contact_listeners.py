# In src/events/contact_listeners.py

from .event_types import NameCaptureEvent, BaseEvent
from ..crud import crud_contact, crud_tag
import re

def _slugify_tag(text: str) -> str:
    """Helper to convert a service name into a slug format."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", '', text)
    text = re.sub(r'[\s-]+', '-', text)
    return text

def update_contact_name(event: NameCaptureEvent):
    """LISTENER: Updates the contact's name in the database."""
    print("  [Listener]: Running update_contact_name...")
    extracted_name = event.analysis.get("action_params", {}).get("customer_name")
    if extracted_name and not event.contact.is_name_confirmed:
        crud_contact.update_contact_name(
            db=event.db_session,
            contact_id=event.contact.contact_id,
            new_name=extracted_name
        )
        event.db_session.commit()

def apply_suggested_tags(event: BaseEvent):
    """LISTENER: Applies any tags suggested by the AI. Runs for most events."""
    print("  [Listener]: Running apply_suggested_tags...")
    tags_to_apply = set(event.analysis.get("tags", []))
    
    # --- THIS IS THE NEW, SMARTER LOGIC ---
    # Check if the AI identified a specific service entity
    entities = event.analysis.get("action_params", {}) # Or "entities" depending on final AI prompt
    service_name = entities.get("service")
    
    if service_name:
        # If a specific service was found, generate a specific interest tag for it.
        specific_tag = f"interest:{_slugify_tag(service_name)}"
        print(f"   -> Service entity '{service_name}' found. Generating specific tag: '{specific_tag}'")
        tags_to_apply.add(specific_tag)

    
    if tags_to_apply:
        crud_tag.update_tags_for_contact(
            db=event.db_session,
            contact_id=event.contact.contact_id,
            tag_names=list(tags_to_apply)
        )
    