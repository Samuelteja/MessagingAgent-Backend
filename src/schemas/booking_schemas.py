# src/schemas/booking_schemas.py

from pydantic import BaseModel, ConfigDict
from datetime import datetime

class BookingBase(BaseModel):
    service_name: str
    booking_datetime: datetime
    status: str = "confirmed"

class BookingCreate(BookingBase):
    contact_db_id: int

class Booking(BookingBase):
    id: int
    contact_db_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)