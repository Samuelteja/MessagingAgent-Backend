# In src/controllers/reconciliation_controller.py

from sqlalchemy.orm import Session
from ..schemas import webhook_schemas
from ..services import ai_service, whatsapp_service
from ..crud import crud_delivery

def process_manager_reconciliation(message: webhook_schemas.NormalizedMessage, db: Session):
    """
    Handles a reply from a manager, parses it for reconciliation data,
    and updates the database.
    """
    manager_reply = message.body
    manager_contact_id = message.contact_id
    
    # 1. Call Dany's AI tool to parse the free-form text into structured data.
    # NOTE: This assumes a new function in ai_service that Dany will provide.
    parsed_data = ai_service.parse_manager_reply(manager_reply)
    
    confirmed_ids = parsed_data.get("confirmed_ids", [])
    failed_ids = parsed_data.get("failed_ids", [])
    
    # 2. Check if the AI was able to extract any useful information.
    if not confirmed_ids and not failed_ids:
        error_message = "Sorry, I couldn't understand that response. Please use the format 'OK 123 125 FAIL 124' to reconcile the deliveries."
        whatsapp_service.send_reply(manager_contact_id, error_message)
        return

    # 3. Perform the bulk database update.
    updated_count = crud_delivery.bulk_update_delivery_statuses(db, confirmed_ids, failed_ids)
    
    # 4. Send a confirmation message back to the manager.
    confirmation_message = (
        f"✅ Reconciliation complete.\n"
        f"Processed: {updated_count} records.\n"
        f"Confirmed: {len(confirmed_ids)}\n"
        f"Failed: {len(failed_ids)}"
    )
    whatsapp_service.send_reply(manager_contact_id, confirmation_message)