# src/schemas/profile_schemas.py

from pydantic import BaseModel
from typing import Optional

class ProfileBase(BaseModel):
    business_name: str
    business_description: Optional[str] = None
    address: Optional[str] = None
    phone_number: Optional[str] = None

class ProfileUpdate(ProfileBase):
    pass

class Profile(ProfileBase):
    id: int
    business_type: str
    class Config:
        from_attributes = True