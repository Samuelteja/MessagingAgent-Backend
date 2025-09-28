# In src/crud/crud_delivery.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from datetime import date
from typing import List, Dict
from .. import models

def create_delivery_list(db: Session, delivery_date: date, file_name: str) -> models.DeliveryList:
    """
    Creates the parent delivery list for a given day.
    Raises ValueError on duplicate to be caught by the router.
    """
    db_list = models.DeliveryList(delivery_date=delivery_date, file_name=file_name)
    db.add(db_list)
    try:
        # We commit here to ensure the parent list exists before adding children
        # and to trigger the unique constraint check immediately.
        db.commit()
        db.refresh(db_list)
        return db_list
    except IntegrityError:
        db.rollback()
        # This specific error will be caught by the router for a clean 409 response
        raise ValueError(f"A delivery list for the date {delivery_date} already exists.")

def create_daily_deliveries_bulk(db: Session, delivery_list_id: int, deliveries_data: List[Dict]):
    """Bulk inserts all delivery items from the parsed file."""
    db_deliveries = [
        models.DailyDelivery(
            delivery_list_id=delivery_list_id,
            customer_phone=row['customer_phone'],
            customer_name=row['customer_name'],
            customer_address=row['customer_address']
        ) for row in deliveries_data
    ]
    db.bulk_save_objects(db_deliveries)
    db.commit()

def get_deliveries_by_date(db: Session, delivery_date: date) -> List[models.DailyDelivery]:
    """
    Fetches all individual delivery items for a specific date by finding the
    parent DeliveryList for that date.
    """
    # Find the parent list for the given date. We use joinedload to eagerly
    # fetch all the 'deliveries' in a single, efficient query.
    delivery_list = (
        db.query(models.DeliveryList)
        .options(joinedload(models.DeliveryList.deliveries))
        .filter(models.DeliveryList.delivery_date == delivery_date)
        .first()
    )

    if not delivery_list:
        # If no list was uploaded for that day, return an empty list.
        return []

    return delivery_list.deliveries