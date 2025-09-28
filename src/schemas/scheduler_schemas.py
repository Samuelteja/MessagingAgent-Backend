# src/schemas/scheduler_schemas.py

from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class ScheduledTaskBase(BaseModel):
    contact_id: str
    task_type: str
    scheduled_time: datetime
    content: Optional[str] = None
    status: str

class ScheduledTask(ScheduledTaskBase):
    id: int
    model_config = ConfigDict(from_attributes=True)