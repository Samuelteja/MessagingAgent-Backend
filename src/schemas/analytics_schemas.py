# src/analytics_schemas.py.
from pydantic import BaseModel
from typing import List, Dict

class DailyStat(BaseModel):
    date: str
    count: int

class OutcomeStat(BaseModel):
    outcome: str
    count: int

class AnalyticsSummary(BaseModel):
    total_conversations: int
    total_bookings_confirmed: int
    total_handoffs: int
    conversations_per_day: List[DailyStat]
    outcomes_breakdown: List[OutcomeStat]

class ServiceBookingStat(BaseModel):
    service_name: str
    booking_count: int
    estimated_revenue: float

class AdvancedAnalytics(BaseModel):
    total_estimated_revenue: float
    avg_revenue_per_booking: float
    top_booked_services: List[ServiceBookingStat]