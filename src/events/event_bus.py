# In src/events/event_bus.py

from typing import Callable, List, Dict, Type
from .event_types import BaseEvent

# The registry mapping event types to their listener pipelines
EVENT_LISTENERS: Dict[Type[BaseEvent], List[Callable]] = {}

def register_listener(event_type: Type[BaseEvent], listener_func: Callable):
    """Adds a listener function to an event's pipeline."""
    if event_type not in EVENT_LISTENERS:
        EVENT_LISTENERS[event_type] = []
    EVENT_LISTENERS[event_type].append(listener_func)
    print(f"Registered listener '{listener_func.__name__}' for event '{event_type.__name__}'")

def dispatch(event: BaseEvent):
    """
    Executes the pipeline for a given event, stopping if a listener
    sets the 'stop_processing' flag.
    """
    pipeline = EVENT_LISTENERS.get(type(event), [])
    print(f"Dispatching event '{type(event).__name__}' through a pipeline of {len(pipeline)} listeners...")
    
    for listener in pipeline:
        if event.stop_processing:
            print(f"-> Pipeline stopped by '{event.stop_reason}'.")
            break
        listener(event)
    
    print("-> Event dispatch finished.")