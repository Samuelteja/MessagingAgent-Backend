# src/crud/crud_booking.py

from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from .. import models
from ..schemas import booking_schemas
from typing import List

def create_booking(db: Session, contact_db_id: int, service_name: str, booking_datetime: datetime) -> models.Booking:
    """
    Creates a new booking record in the database for a specific contact.
    """
    print(f"DB: Creating booking for contact ID {contact_db_id} for service '{service_name}' at {booking_datetime}")
    
    db_booking = models.Booking(
        contact_db_id=contact_db_id,
        service_name=service_name,
        booking_datetime=booking_datetime,
        status="confirmed"
    )
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    
    print(f"   - Booking successfully created with ID: {db_booking.id}")
    return db_booking

def get_most_recent_booking(db: Session, contact_db_id: int) -> models.Booking:
    """
    Fetches the single most recent booking for a contact, ordered by creation time.
    """
    return db.query(models.Booking).filter(
        models.Booking.contact_db_id == contact_db_id
    ).order_by(models.Booking.created_at.desc()).first()

def get_bookings_by_contact_id(db: Session, contact_db_id: int) -> List[models.Booking]:
    """
    Fetches all booking records for a specific contact, ordered by the
    booking time.
    """
    return (
        db.query(models.Booking)
        .filter(models.Booking.contact_db_id == contact_db_id)
        .order_by(models.Booking.booking_datetime.asc())
        .all()
    )

def get_recent_and_upcoming_bookings(db: Session, contact_db_id: int) -> List[models.Booking]:
    """
    Fetches all bookings for a contact that are either in the future or were
    booked in the last 7 days. This provides context for the AI.
    """
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    
    return (
        db.query(models.Booking)
        .filter(
            models.Booking.contact_db_id == contact_db_id,
            models.Booking.booking_datetime >= seven_days_ago # Only fetch recent/future bookings
        )
        .order_by(models.Booking.booking_datetime.asc())
        .all()
    )