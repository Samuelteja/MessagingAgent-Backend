# src/routers/bookings_router.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from ..schemas import booking_schemas
from ..crud import crud_booking, crud_contact
from ..database import SessionLocal

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


# --- API Endpoint ---

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