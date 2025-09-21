# src/routers/analytics_router.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..schemas import analytics_schemas
from ..crud import crud_analytics
from ..database import SessionLocal

router = APIRouter(
    prefix="/api/analytics", # Use a more specific prefix
    tags=["Analytics"]
)

# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# The path is now "/summary"
@router.get("/summary", response_model=analytics_schemas.AnalyticsSummary, summary="Get Dashboard Analytics Summary")
def get_analytics(db: Session = Depends(get_db)):
    return crud_analytics.get_analytics_summary(db)

# The path is now "/advanced"
@router.get("/advanced", response_model=analytics_schemas.AdvancedAnalytics, summary="Get Advanced ROI Analytics")
def get_advanced_analytics_data(db: Session = Depends(get_db)):
    return crud_analytics.get_advanced_analytics(db)