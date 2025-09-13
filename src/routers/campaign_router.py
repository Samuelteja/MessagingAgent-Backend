from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..schemas import campaign_schemas
from ..crud import crud_campaign, crud_contact # find_contacts_by_tags is in crud_contact
from ..database import SessionLocal
import random

router = APIRouter(
    prefix="/api/campaigns",
    tags=["Campaigns"]
)

# --- CONFIGURATION (Should be in a central config file later) ---
MAX_BROADCASTS_PER_DAY = 100
MIN_STAGGER_SECONDS = 45
MAX_STAGGER_SECONDS = 120

# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# The path is now "/broadcast"
@router.post("/broadcast", summary="Launch a Smart Broadcast Campaign")
def launch_smart_campaign(payload: campaign_schemas.CampaignCreatePayload, db: Session = Depends(get_db)):
    print(f"Received request to launch campaign: '{payload.name}'")

    sent_today = crud_campaign.count_campaign_messages_sent_today(db)
    remaining_sends = MAX_BROADCASTS_PER_DAY - sent_today
    if remaining_sends <= 0:
        raise HTTPException(status_code=429, detail=f"Daily broadcast limit reached.")

    # find_contacts_by_tags is now in crud_contact
    target_contacts = crud_contact.find_contacts_by_tags(db, payload.target_tags)
    if not target_contacts:
        raise HTTPException(status_code=404, detail="No customers found matching tags.")
    
    campaign = crud_campaign.create_campaign(db, name=payload.name, message_template=payload.message_template, expires_at=payload.expires_at)
    
    scheduling_result = crud_campaign.add_and_schedule_recipients(
        db,
        campaign=campaign,
        contacts=target_contacts,
        stagger_seconds=random.randint(MIN_STAGGER_SECONDS, MAX_STAGGER_SECONDS),
        daily_limit=remaining_sends
    )

    return {
        "status": "success",
        "message": f"Campaign '{campaign.name}' has been successfully scheduled.",
        "summary": scheduling_result
    }