# In src/crud/crud_delivery.py

from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, case
from datetime import date, datetime, timezone
from typing import List, Dict, Optional
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

def get_deliveries_by_date(
    db: Session,
    delivery_date: date,
    search_term: Optional[str] = None,
    status: Optional[str] = None
) -> List[models.DailyDelivery]:
    """
    REFACTORED: Fetches all individual delivery items for a specific date,
    now with optional filters for search and status.
    """
    query = (
        db.query(models.DailyDelivery)
        .join(models.DeliveryList)
        .filter(models.DeliveryList.delivery_date == delivery_date)
    )

    if status:
        query = query.filter(models.DailyDelivery.status == status)

    if search_term:
        search_filter = f"%{search_term}%"
        query = query.filter(
            or_(
                models.DailyDelivery.customer_name.ilike(search_filter),
                models.DailyDelivery.customer_phone.ilike(search_filter)
            )
        )

    return query.order_by(models.DailyDelivery.id.asc()).all()

def get_unreconciled_deliveries_by_date(db: Session, delivery_date: date) -> List[models.DailyDelivery]:
    """
    Finds all deliveries for a specific date that are still in the
    'pending_reconciliation' state. This is used to build the prompt for the manager.
    """
    return (
        db.query(models.DailyDelivery)
        .join(models.DeliveryList)
        .filter(
            models.DeliveryList.delivery_date == delivery_date,
            models.DailyDelivery.status == 'pending_reconciliation'
        )
        .all()
    )

def update_delivery_status(
    db: Session,
    delivery_id: int,
    status: str,
    failure_reason: Optional[str] = None
) -> Optional[models.DailyDelivery]:
    """
    Updates the status and optional failure reason for a SINGLE delivery record.
    This is used for manual reconciliation from the dashboard.
    """
    db_delivery = db.query(models.DailyDelivery).filter(models.DailyDelivery.id == delivery_id).first()

    if not db_delivery:
        return None

    db_delivery.status = status
    db_delivery.failure_reason = failure_reason
    db_delivery.reconciliation_timestamp = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(db_delivery)
    
    print(f"DB: Manually updated status for Delivery ID {delivery_id} to '{status}'.")
    return db_delivery

def bulk_update_delivery_statuses(db: Session, confirmed_ids: List[int], failed_ids: List[int]) -> int:
    """
    Performs a high-performance bulk update of delivery statuses based on the parsed
    manager's reply.
    """
    if not confirmed_ids and not failed_ids:
        return 0

    # This single query updates all relevant records at once.
    db.query(models.DailyDelivery).filter(models.DailyDelivery.id.in_(confirmed_ids + failed_ids)).update(
        {
            models.DailyDelivery.status: case(
                (models.DailyDelivery.id.in_(confirmed_ids), "reconciled_confirmed"),
                (models.DailyDelivery.id.in_(failed_ids), "reconciled_failed"),
            ),
            models.DailyDelivery.reconciliation_timestamp: datetime.now(timezone.utc)
        },
        synchronize_session=False
    )
    
    db.commit()
    
    total_updated = len(confirmed_ids) + len(failed_ids)
    print(f"DB: Bulk updated {total_updated} delivery statuses.")
    return total_updated