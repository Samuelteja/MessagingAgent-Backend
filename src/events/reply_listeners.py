# In src/events/reply_listeners.py

from .event_types import BaseEvent

def generate_reply_from_suggestion(event: BaseEvent):
    """
    LISTENER: The default reply generator. It sets the final_reply
    to whatever the AI suggested. This is used for simple events like
    Inquiry, Greeting, NameCapture, etc.
    """
    if event.final_reply is None: # Only run if a reply hasn't already been set
        print("  [Listener]: Running generate_reply_from_suggestion...")
        event.final_reply = event.analysis.get("spoken_reply_suggestion", "I'm not sure how to respond to that, sorry!")
    