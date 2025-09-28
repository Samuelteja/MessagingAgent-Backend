# In src/schemas/booking_schemas.py

from pydantic import BaseModel, ConfigDict, computed_field
from typing import Optional
from datetime import datetime
from .contact_schemas import Contact
from .knowledge_schemas import StaffRoster
from .menu_schemas import MenuItem

class ManualBookingPayload(BaseModel):
    customer_phone: str
    customer_name: str
    service_name: str
    booking_datetime: datetime
    end_datetime: Optional[datetime] = None
    notes: Optional[str] = None
    staff_id: Optional[int] = None

class BookingBase(BaseModel):
    booking_datetime: datetime
    end_datetime: Optional[datetime] = None
    notes: Optional[str] = None
    staff_db_id: Optional[int] = None

class BookingCreate(BookingBase):
    contact_db_id: int

class Booking(BookingBase):
    id: int
    contact_db_id: int
    source: str
    status: str
    created_at: datetime
    service_id: Optional[int] = None
    service_name_text: str

    @computed_field
    @property
    def service_name(self) -> str:
        return self.service_name_text
    
    model_config = ConfigDict(from_attributes=True)

class BookingWithDetails(Booking):
    """Extends the base Booking schema to include full nested objects for related data."""
    contact: Optional[Contact] = None
    staff: Optional[StaffRoster] = None
    service: Optional[MenuItem] = None

    model_config = ConfigDict(from_attributes=True)

class CalendarBooking(BaseModel):
    id: int
    title: str
    start: datetime
    end: datetime
    staff_name: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: str
    service_id: Optional[int] = None
    service_name: str
    
    model_config = ConfigDict(from_attributes=True)

class BookingUpdate(BaseModel):
    service_id: Optional[int] = None 
    booking_datetime: datetime
    end_datetime: Optional[datetime] = None
    notes: Optional[str] = None
    staff_id: Optional[int] = None
    # Note: We do not include customer_phone/name here, as we will handle
    # re-assigning a booking to a different customer as a separate, more
    # complex feature in the future. For now, an edit applies to the existing customer.

