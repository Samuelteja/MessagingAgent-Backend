# In src/schemas/delivery_schemas.py

from pydantic import BaseModel, ConfigDict
from typing import Optional

class DailyDelivery(BaseModel):
    id: int
    customer_name: Optional[str] = None
    customer_phone: str
    customer_address: Optional[str] = None
    status: str

    model_config = ConfigDict(from_attributes=True)