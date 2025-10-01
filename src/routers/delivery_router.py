# In src/routers/delivery_router.py

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from ..database import SessionLocal
import pandas as pd
import io
from datetime import date, datetime
import random
from ..schemas import delivery_schemas
from ..crud import crud_delivery
from typing import List, Optional

# --- NEW: Import all necessary CRUD modules and services ---
from ..crud import crud_delivery, crud_campaign, crud_contact
from ..schemas import campaign_schemas, delivery_schemas

class DeliveryStatusUpdate(delivery_schemas.BaseModel):
    status: str
    failure_reason: Optional[str] = None

router_deliveries = APIRouter(
    prefix="/api/deliveries",
    tags=["Deliveries"]
)

router_delivery_lists = APIRouter(
    prefix="/api/delivery-lists",
    tags=["Delivery Lists"]
)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@router_deliveries.patch("/{delivery_id}/status", response_model=delivery_schemas.DailyDelivery)
def patch_delivery_status(
    delivery_id: int,
    payload: DeliveryStatusUpdate,
    db: Session = Depends(get_db)
):
    """
    Manually update the status of a single delivery item.
    Used by the manager's reconciliation dashboard.
    """
    updated_delivery = crud_delivery.update_delivery_status(
        db,
        delivery_id=delivery_id,
        status=payload.status,
        failure_reason=payload.failure_reason
    )
    if not updated_delivery:
        raise HTTPException(status_code=404, detail="Delivery record not found.")
    return updated_delivery

@router_delivery_lists.post("/upload", summary="Upload Daily Delivery List & Trigger Broadcast")
async def upload_delivery_list(
    delivery_date: date = Form(...),
    file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    """
    Handles the upload, parsing, saving, and automatic broadcast scheduling
    for a Gas Distributor's daily delivery list.
    """
    if not file.filename or not file.filename.lower().endswith(('.csv', '.xlsx')):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a CSV or Excel file.")

    try:
        contents = await file.read()

        if file.filename.lower().endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            cleaned = contents.replace(b'"', b'')
            df = pd.read_csv(io.BytesIO(cleaned), dtype={"customer_phone": str}, engine="python", sep=",")
            df.columns = [c.strip() for c in df.columns]

        required_columns = ['customer_phone', 'customer_name', 'customer_address']
        missing = [c for c in required_columns if c not in df.columns]
        if missing:
            raise HTTPException(status_code=400, detail=f"File is missing required columns: {missing}")

        # --- STEP 1: Create the parent DeliveryList (handles idempotency) ---
        try:
            delivery_list = crud_delivery.create_delivery_list(db, delivery_date=delivery_date, file_name=file.filename)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create delivery list: {e}")

        # --- STEP 2: Create the individual delivery items ---
        deliveries_to_create = df.to_dict(orient='records')
        try:
            crud_delivery.create_daily_deliveries_bulk(db, delivery_list_id=delivery_list.id, deliveries_data=deliveries_to_create)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create daily deliveries: {e}")

        # --- STEP 3: Trigger the morning confirmation broadcast automation ---
        contacts_to_message = []
        for d in deliveries_to_create:
            try:
                contact = crud_contact.get_or_create_contact(
                    db,
                    contact_id=str(d['customer_phone']),
                    pushname=d.get('customer_name')
                )
                contacts_to_message.append(contact)
            except Exception:
                continue  # skip bad contacts silently

        campaign_name = f"Delivery Confirmation - {delivery_date.strftime('%Y-%m-%d')}"
        message_template = (
            "Hi {customer_name}, this is a confirmation from [Gas Company]. "
            "Your cylinder is scheduled for delivery today. "
            "Please ensure someone is available at your address to receive it."
        )
        expires_at = datetime.combine(delivery_date, datetime.max.time())
        try:
            campaign = crud_campaign.create_campaign(
                db,
                name=campaign_name,
                message_template=message_template,
                expires_at=expires_at
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create campaign: {e}")

        try:
            crud_campaign.add_and_schedule_recipients(
                db,
                campaign=campaign,
                contacts=contacts_to_message,
                stagger_seconds=random.randint(45, 120),
                daily_limit=1000 
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to schedule broadcast: {e}")

        return {
            "message": f"Delivery List {file.filename} uploaded successfully!",
            "summary": {
                "total_parsed": len(df),
                "new_customers_created": len(contacts_to_message),
                "confirmations_scheduled": len(contacts_to_message)
            }
        }

    except HTTPException as e:
        raise e  # Re-raise known HTTP exceptions
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")
    
@router_delivery_lists.get("/{delivery_date}", response_model=List[delivery_schemas.DailyDelivery])
def get_daily_deliveries_by_date_with_filters(
    delivery_date: date,
    search_term: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Retrieves the list of delivery items for a specific date, with optional
    filters for search and status.
    """
    deliveries = crud_delivery.get_deliveries_by_date(
        db,
        delivery_date=delivery_date,
        search_term=search_term,
        status=status
    )
    return deliveries

@router_delivery_lists.get("/{delivery_date}", response_model=List[delivery_schemas.DailyDelivery], summary="Get Daily Deliveries by Date")
def get_daily_deliveries_by_date(delivery_date: date, db: Session = Depends(get_db)):

    """
    Retrieves the full list of delivery items for a specific date,
    intended for display on the Gas Distributor's daily operations dashboard.
    """
    deliveries = crud_delivery.get_deliveries_by_date(db, delivery_date=delivery_date)
    
    # Note: Because our Pydantic schema in delivery_schemas.py is well-defined,
    # FastAPI will automatically handle the conversion from the SQLAlchemy objects
    # to the required JSON structure. The 'customer_phone' field will be correctly
    # serialized from the model.
    
    return deliveries