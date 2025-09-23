# src/routers/scheduler_router.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from ..schemas import scheduler_schemas
from ..crud import crud_scheduler
from ..database import SessionLocal

router = APIRouter(prefix="/api/scheduled-tasks", tags=["Scheduled Tasks"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@router.get("/", response_model=List[scheduler_schemas.ScheduledTask])
def read_pending_tasks(db: Session = Depends(get_db)):
    """
    Fetches all tasks from the scheduled_tasks table with a status of 'pending'.
    This is for the 'Scheduled Outreach' UI.
    """
    return crud_scheduler.get_pending_tasks(db)