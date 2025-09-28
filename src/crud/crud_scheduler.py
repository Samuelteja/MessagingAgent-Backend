# src/crud/crud_scheduler.py

from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Optional
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

def get_reminder_for_booking(db: Session, contact_id: str, booking_datetime: datetime) -> Optional[models.ScheduledTask]:
    """
    Finds a specific APPOINTMENT_REMINDER for a given contact and booking time.
    This is more precise than a wide time window.
    """
    # The reminder is scheduled for exactly 24 hours before the booking.
    expected_reminder_time = booking_datetime - timedelta(hours=24)
    print(f"DB: Looking for reminder for contact {contact_id} at {expected_reminder_time} and booking at {booking_datetime}")
    return db.query(models.ScheduledTask).filter(
        models.ScheduledTask.contact_id == contact_id,
        models.ScheduledTask.task_type == 'APPOINTMENT_REMINDER',
        models.ScheduledTask.status == 'pending'
    ).first()

def update_scheduled_task(db: Session, task_id: int, new_scheduled_time: datetime, new_content: str) -> Optional[models.ScheduledTask]:
    """Updates the time and content of an existing scheduled task."""
    db_task = db.query(models.ScheduledTask).filter(models.ScheduledTask.id == task_id).first()
    if db_task:
        db_task.scheduled_time = new_scheduled_time
        db_task.content = new_content
        print(f"   - Scheduled Task #{task_id} has been updated in the session.")
    return db_task

def delete_scheduled_task(db: Session, task_id: int):
    """Deletes a scheduled task by its ID."""
    db_task = db.query(models.ScheduledTask).filter(models.ScheduledTask.id == task_id).first()
    if db_task:
        db.delete(db_task)
        print(f"   - Scheduled Task #{task_id} has been deleted from the session.")