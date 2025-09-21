# src/schemas/campaign_schemas.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import time, datetime

class CampaignCreatePayload(BaseModel):
    name: str = Field(..., example="July Discount Offer")
    message_template: str = Field(..., example="Hi {customer_name}! Get 15% off this week.")
    target_tags: List[str] = Field(..., example=["interest:hair-coloring", "VIP"])
    expires_at: datetime
