# src/routers/bookings_router.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, relationship
from typing import List, Optional
from datetime import datetime, timedelta
from ..schemas import booking_schemas
from ..crud import crud_booking, crud_contact, crud_scheduler
from ..database import SessionLocal
from ..services import whatsapp_service
from .. import models

router = APIRouter(
    prefix="/api/bookings",
    tags=["Bookings"]
)

# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/contact/{contact_id:path}", response_model=List[booking_schemas.Booking], summary="Get All Bookings for a Contact")
def read_bookings_for_contact(contact_id: str, db: Session = Depends(get_db)):
    """
    Retrieves all booking records for a specific contact ID.
    Returns an empty list if the contact has no bookings.
    """
    # First, we need to get the contact's integer PK from their string ID
    contact = crud_contact.get_contact_by_contact_id(db, contact_id=contact_id)
    
    if not contact:
        # If the contact doesn't even exist, they certainly have no bookings.
        return []
        
    return crud_booking.get_bookings_by_contact_id(db, contact_db_id=contact.id)

@router.post("/", response_model=booking_schemas.Booking, summary="Create a Manual Booking")
def create_manual_booking_endpoint(payload: booking_schemas.ManualBookingPayload, db: Session = Depends(get_db)):
    """
    Handles the creation of a manual booking, relying on the CRUD layer for validation.
    """
    contact = crud_contact.get_or_create_contact(db, contact_id=payload.customer_phone, pushname=payload.customer_name)
    
    try:
        new_booking = crud_booking.create_booking(
            db=db,
            contact_db_id=contact.id,
            staff_db_id=payload.staff_id,
            service_name=payload.service_name,
            booking_datetime=payload.booking_datetime,
            end_datetime=payload.end_datetime,
            notes=payload.notes,
            source="manual_booking"
        )
        
        db.commit()
        db.refresh(new_booking)
        db.refresh(contact)
        
        try:
            confirmation_message = (
                f"Hi {contact.name or 'there'}! Your appointment for a '{new_booking.service_name_text}' "
                f"on {new_booking.booking_datetime.strftime('%A, %B %d')} "
            )
            whatsapp_service.send_reply(contact.contact_id, confirmation_message)
        except Exception as e:
            print(f"❌ WARNING: Failed to send manual booking confirmation. Error: {e}")
            
        return new_booking

    except ValueError as e:
        raise HTTPException(
            status_code=409,
            detail=str(e)
        )


@router.put("/{booking_id}", response_model=booking_schemas.Booking, summary="Update an Existing Booking")
def update_existing_booking(
    booking_id: int,
    payload: booking_schemas.BookingUpdate,
    db: Session = Depends(get_db)
):
    """
    Updates a booking and intelligently reschedules or deletes the
    corresponding 24-hour reminder. Also notifies the customer of the change.
    """
    # First, get the original booking to compare dates
    original_booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not original_booking:
        raise HTTPException(status_code=404, detail="Booking not found.")

    original_booking_datetime = original_booking.booking_datetime
    
    # Update the booking details in the session
    updated_booking = crud_booking.update_booking(db, booking_id=booking_id, booking_update=payload)
    
    if updated_booking.booking_datetime != original_booking_datetime:
        print("   - Booking time has changed. Re-scheduling reminder...")
        
        old_reminder = crud_scheduler.get_reminder_for_booking(db, contact_id=updated_booking.contact.contact_id, booking_datetime=original_booking_datetime)
        
        if old_reminder:
            crud_scheduler.delete_scheduled_task(db, task_id=old_reminder.id)

        # 3. Create a new reminder for the new booking time
        new_reminder_time = updated_booking.booking_datetime - timedelta(hours=24)
        new_reminder_content = f"Hi {updated_booking.contact.name or 'there'}! Just a note, your appointment for a {updated_booking.service_name_text} has been updated to {updated_booking.booking_datetime.strftime('%A at %I:%M %p')}. We'll send a reminder the day before."
        crud_scheduler.create_scheduled_task(db, updated_booking.contact.contact_id, "APPOINTMENT_REMINDER", new_reminder_time, new_reminder_content)

    db.commit()
    db.refresh(updated_booking)
    
    # 4. Notify the customer of the change immediately
    try:
        notification_message = (
            f"Hi {updated_booking.contact.name or 'there'}, please note your appointment has been updated.\n\n"
            f"Service: {updated_booking.service_name_text}\n"
            f"New Date & Time: {updated_booking.booking_datetime.strftime('%A, %B %d at %I:%M %p')}\n\n"
            f"If this change wasn't requested by you, please contact us immediately."
        )
        whatsapp_service.send_reply(updated_booking.contact.contact_id, notification_message)
        print("   - Successfully sent booking update notification.")
    except Exception as e:
        print(f"   - WARNING: Failed to send booking update notification for Booking #{updated_booking.id}. Error: {e}")
    
    return updated_booking

@router.get("/", response_model=List[booking_schemas.BookingWithDetails], summary="Get Bookings with Advanced Filters")
def read_bookings_with_filters(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    contact_id: Optional[str] = None,
    staff_id: Optional[int] = None,
    service_name: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Retrieves a list of bookings based on a combination of optional filters.
    This is the primary endpoint for BOTH the "Bookings History" page and the Calendar view.
    The frontend is responsible for transforming this rich data into calendar events if needed.
    """

    # We call the single, powerful CRUD function that does all the work.
    bookings = crud_booking.get_bookings_with_filters(
        db, start_date, end_date, contact_id, staff_id, service_name, status
    )
    
    # The response model `BookingWithDetails` ensures all necessary data (contact, staff, service)
    # is included for any UI rendering purpose.
    return bookings

@router.get("/all", response_model=List[booking_schemas.BookingWithDetails], summary="Get Paginated Booking History with Filters")
def read_all_bookings_history(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    search_term: Optional[str] = None,
    staff_id: Optional[int] = None,
    service_name: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    Provides a paginated and filterable list of all bookings. This is the
    primary endpoint for the "All Bookings History" page.
    """
    bookings = crud_booking.get_bookings_with_filters(
        db=db,
        start_date=start_date,
        end_date=end_date,
        search_term=search_term,
        staff_id=staff_id,
        service_name=service_name,
        status=status,
        skip=skip,
        limit=limit
    )
    return bookings