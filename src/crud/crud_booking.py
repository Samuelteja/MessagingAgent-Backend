# src/crud/crud_booking.py

from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from .. import models
from ..schemas import booking_schemas

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