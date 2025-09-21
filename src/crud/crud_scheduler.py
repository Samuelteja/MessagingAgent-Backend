# src/crud/crud_scheduler.py

from sqlalchemy.orm import Session
from datetime import datetime
from .. import models

def create_scheduled_task(db: Session, contact_id: str, task_type: str, scheduled_time: datetime, content: str = None) -> models.ScheduledTask:
    """
    Creates a new task in the scheduled_tasks table.
    """
    print(f"DB: Scheduling task '{task_type}' for contact {contact_id} at {scheduled_time}")

    db_task = models.ScheduledTask(
        contact_id=contact_id,
        task_type=task_type,
        scheduled_time=scheduled_time,
        content=content,
        status="pending"
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    
    print(f"   - Scheduled task created with ID: {db_task.id}")
    return db_task