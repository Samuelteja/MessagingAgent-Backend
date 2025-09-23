# src/crud/crud_scheduler.py

from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List
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

def get_existing_reminder(db: Session, contact_id: str, appointment_time: datetime) -> models.ScheduledTask:
    """
    Checks if a reminder already exists for a contact within a 4-hour window
    of the proposed appointment time. This prevents duplicate reminders.
    """
    # The reminder is sent 24 hours before the appointment.
    proposed_reminder_time = appointment_time - timedelta(hours=24)
    time_window_start = proposed_reminder_time - timedelta(hours=3)
    time_window_end = proposed_reminder_time + timedelta(hours=3)

    return db.query(models.ScheduledTask).filter(
        models.ScheduledTask.contact_id == contact_id,
        models.ScheduledTask.task_type == 'APPOINTMENT_REMINDER',
        models.ScheduledTask.scheduled_time.between(time_window_start, time_window_end)
    ).first()

def get_pending_tasks(db: Session) -> List[models.ScheduledTask]:
    """
    Fetches all tasks currently in a 'pending' state, ordered by when they
    are scheduled to run.
    """
    return (
        db.query(models.ScheduledTask)
        .filter(models.ScheduledTask.status == 'pending')
        .order_by(models.ScheduledTask.scheduled_time.asc())
        .all()
    )