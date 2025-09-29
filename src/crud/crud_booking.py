# src/crud/crud_booking.py

from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timezone, timedelta
from .. import models
from ..schemas import booking_schemas
from typing import List, Optional

def _get_conflicting_customer_booking(db: Session, contact_db_id: int, service_name: str, booking_datetime: datetime) -> Optional[models.Booking]:
    """
    Checks if the same customer already has a booking for the same service
    within a +/- 2-hour window of the proposed booking time.
    """
    time_window_start = booking_datetime - timedelta(hours=2)
    time_window_end = booking_datetime + timedelta(hours=2)

    return db.query(models.Booking).filter(
        models.Booking.contact_db_id == contact_db_id,
        models.Booking.service_name_text == service_name,
        models.Booking.booking_datetime.between(time_window_start, time_window_end)
    ).first()


def create_booking(
    db: Session,
    contact_db_id: int,
    service_name: str,
    booking_datetime: datetime,
    end_datetime: Optional[datetime] = None,
    notes: Optional[str] = None,
    staff_db_id: Optional[int] = None,
    source: str = "ai_booking" # Default to AI, can be overridden
) -> models.Booking:
    """
    Creates a new booking record after performing a mandatory duplicate check.
    This is the single, authoritative function for creating all bookings.
    Raises ValueError if a conflicting booking is found.
    """
    # 1. Perform the mandatory duplicate check
    existing_booking = _get_conflicting_customer_booking(db, contact_db_id, service_name, booking_datetime)
    
    if existing_booking:
        raise ValueError(
            f"Duplicate Booking: This customer already has a booking for '{service_name}' "
            f"at {existing_booking.booking_datetime.strftime('%I:%M %p')}."
        )
    menu_item = db.query(models.MenuItem).filter(models.MenuItem.name == service_name).first()
    service_id = menu_item.id if menu_item else None
    # 2. If no conflict, create the new booking object
    db_booking = models.Booking(
        contact_db_id=contact_db_id,
        staff_db_id=staff_db_id,
        service_id=service_id,
        service_name_text=service_name,
        booking_datetime=booking_datetime,
        end_datetime=end_datetime,
        notes=notes,
        source=source,
        status="confirmed"
    )
    db.add(db_booking)
    print(f"DEBUG: Booking #{db_booking.id} for {service_name} IS NOW IN SESSION. Pending commit.")
    print(f"DEBUG: Session dirty objects: {db.dirty}")
    print(f"DEBUG: Session new objects: {db.new}")
    return db_booking

def get_most_recent_booking(db: Session, contact_db_id: int) -> models.Booking:
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

def create_manual_booking(db: Session, contact_db_id: int, booking_payload: models.Booking) -> models.Booking:
    """
    Creates a new Booking record from the manual booking form payload.
    """
    db_booking = models.Booking(
        contact_db_id=contact_db_id,
        staff_db_id=booking_payload.staff_id,
        service_name=booking_payload.service_name,
        booking_datetime=booking_payload.booking_datetime,
        end_datetime=booking_payload.end_datetime,
        notes=booking_payload.notes,
        source="manual_booking"
    )
    db.add(db_booking)
    return db_booking

def get_bookings_for_calendar(db: Session, start_date: datetime, end_date: datetime) -> List[models.Booking]:
    """
    Fetches all bookings within a given date range for the calendar view.
    """
    return (
        db.query(models.Booking)
        .options(
            joinedload(models.Booking.contact), # Eager load the contact for the title
            joinedload(models.Booking.staff),    # <-- Eager load the staff for the color-coding
            joinedload(models.Booking.service)   # <-- Eager load the service for potential future use
        )
        .filter(
            models.Booking.booking_datetime >= start_date,
            models.Booking.booking_datetime <= end_date
        )
        .all()
    )

def get_conflicting_customer_booking(db: Session, contact_db_id: int, service_name: str, booking_datetime: datetime) -> models.Booking | None:
    """
    Checks if the same customer already has a booking for the same service
    within a +/- 2-hour window of the proposed booking time.
    """
    time_window_start = booking_datetime - timedelta(hours=2)
    time_window_end = booking_datetime + timedelta(hours=2)

    return db.query(models.Booking).filter(
        models.Booking.contact_db_id == contact_db_id,
        models.Booking.service_name == service_name,
        models.Booking.booking_datetime.between(time_window_start, time_window_end)
    ).first()

def update_booking(db: Session, booking_id: int, booking_update: booking_schemas.BookingUpdate) -> Optional[models.Booking]:
    """
    Updates an existing booking with new details.
    """
    db_booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()

    if not db_booking:
        return None

    db_booking.booking_datetime = booking_update.booking_datetime
    db_booking.end_datetime = booking_update.end_datetime
    db_booking.notes = booking_update.notes
    db_booking.staff_db_id = booking_update.staff_id
    if booking_update.service_id:
        # Find the new menu item to get its name
        new_service = db.query(models.MenuItem).filter(models.MenuItem.id == booking_update.service_id).first()
        if new_service:
            db_booking.service_id = new_service.id
            db_booking.service_name_text = new_service.name
        else:
            # Handle the case where a bad service_id is sent
            # For now, we'll just ignore the change if the ID is invalid
            print(f"   - WARNING: Invalid service_id '{booking_update.service_id}' provided during booking update.")
    
    print(f"   - Booking #{db_booking.id} has been updated in the session.")
    return db_booking

def get_most_recent_booking_by_service(db: Session, contact_db_id: int, service_name: str) -> Optional[models.Booking]:
    """Finds the most recent, confirmed booking for a specific service."""
    return db.query(models.Booking).filter(
        models.Booking.contact_db_id == contact_db_id,
        models.Booking.service_name_text == service_name,
        models.Booking.status == 'confirmed'
    ).order_by(models.Booking.booking_datetime.desc()).first()

def update_booking_time(db: Session, booking_id: int, new_datetime: datetime) -> Optional[models.Booking]:
    """Updates the time of an existing booking."""
    db_booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if db_booking:
        db_booking.booking_datetime = new_datetime
        # Optionally update end_datetime if duration is known
    return db_booking

def get_bookings_with_filters(
    db: Session, 
    start_date: datetime, 
    end_date: datetime, 
    contact_id: Optional[str] = None, 
    staff_id: Optional[int] = None,
    service_name: Optional[str] = None, # <-- NEW PARAMETER
    status: Optional[str] = None # <-- NEW PARAMETER (e.g., 'confirmed', 'cancelled')
) -> List[models.Booking]:
    """
    MODIFIED: Fetches bookings with a more powerful set of filters, including
    by service name and the booking's status.
    """
    query = (
        db.query(models.Booking)
        .options(
            joinedload(models.Booking.contact),
            joinedload(models.Booking.staff),
            joinedload(models.Booking.service)
        )
        .order_by(models.Booking.booking_datetime.desc())
    )

    if start_date:
        query = query.filter(models.Booking.booking_datetime >= start_date)
    if end_date:
        query = query.filter(models.Booking.booking_datetime <= end_date)
    if contact_id:
        query = query.join(models.Contact).filter(models.Contact.contact_id == contact_id)
    if staff_id:
        query = query.filter(models.Booking.staff_db_id == staff_id)
    if service_name:
        query = query.filter(models.Booking.service_name_text.ilike(f"%{service_name}%"))
    if status:
        query = query.filter(models.Booking.status == status)
    
    return query.all()