# src/services/scheduler_service.py

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from ..database import SQLALCHEMY_DATABASE_URL, SessionLocal
import atexit
from datetime import datetime, timezone
from .. import models
from . import whatsapp_service

jobstores = {
    'default': SQLAlchemyJobStore(url=SQLALCHEMY_DATABASE_URL)
}

# --- SCHEDULER INITIALIZATION ---
scheduler = BackgroundScheduler(jobstores=jobstores)

def process_pending_campaign_messages():
    """
    This job runs every minute. It finds scheduled campaign messages that are due
    and sends them via the appropriate service.
    """
    db = SessionLocal()
    try:
        print(f"⏰ [{datetime.now()}] Running scheduler job: Processing pending campaign messages...")
        
        due_recipients = (
            db.query(models.CampaignRecipient)
            .join(models.Campaign)
            .filter(
                models.CampaignRecipient.status == 'scheduled',
                models.CampaignRecipient.safety_check_passed == True,
                models.CampaignRecipient.scheduled_time <= datetime.now(timezone.utc),
                models.Campaign.expires_at > datetime.now(timezone.utc)
            )
            .limit(10) # Process in batches of 10 to avoid overwhelming the system
            .all()
        )

        if not due_recipients:
            print("   - No due campaign messages found.")
            return

        print(f"   - Found {len(due_recipients)} due message(s) to send.")
        for recipient in due_recipients:
            message_to_send = recipient.content

            whatsapp_service.send_reply(recipient.contact_id, message_to_send)
            
            recipient.status = 'sent'
            db.commit()
            print(f"   -> Sent campaign message to {recipient.contact_id}")

    finally:
        db.close()

def cleanup_expired_campaigns():
    """A daily job to mark expired campaigns as 'completed'."""
    db = SessionLocal()
    try:
        expired_campaigns = db.query(models.Campaign).filter(
            models.Campaign.status == 'processing',
            models.Campaign.expires_at <= datetime.now(timezone.utc)
        ).all()

        for campaign in expired_campaigns:
            print(f"🧹 Cleaning up expired campaign: '{campaign.name}'")
            campaign.status = 'completed'
        
        db.commit()
    finally:
        db.close()

def initialize_scheduler():
    """
    Initializes and starts the global scheduler, now with the real job.
    """
    try:
        scheduler.start()
        print("✅ APScheduler started successfully.")
        
        # Add the main job to run every minute
        scheduler.add_job(
            process_pending_campaign_messages,
            'interval',
            minutes=1,
            id='process_campaigns_job',
            replace_existing=True
        )
        
        scheduler.add_job(
            cleanup_expired_campaigns,
            'interval',
            hours=1,
            id='cleanup_campaigns_job',
            replace_existing=True
        )

        atexit.register(lambda: scheduler.shutdown())
        
    except Exception as e:
        print(f"❌ Error starting APScheduler: {e}")

# --- EXAMPLE JOB FUNCTION ---
# This is a placeholder to show how a job is defined. We will create the real
# job functions (send_reminder, send_followup) in the coming days.
def _send_whatsapp_message_job(phone_number: str, message: str):
    """
    This is the function the scheduler will execute at the scheduled time.
    It will eventually call our whatsapp_service to send the message.
    NOTE: We cannot pass a database session directly to a scheduled job.
    The job runs in a separate thread and needs to create its own session.
    """
    print(f"⏰ EXECUTING SCHEDULED JOB: Send '{message}' to {phone_number}")
    # In a future step, this will be:
    # from . import whatsapp_service
    # from ..database import SessionLocal
    # db = SessionLocal()
    # whatsapp_service.send_reply(phone_number, message)
    # db.close()

# --- PUBLIC SCHEDULING FUNCTIONS ---
def schedule_message(phone_number: str, message: str, run_date: datetime):
    """
    Adds a new message-sending job to the scheduler.
    """
    if not isinstance(run_date, datetime):
        raise TypeError("run_date must be a datetime object")

    job_id = f"send_message_{phone_number}_{int(run_date.timestamp())}"
    
    print(f"🗓️ Scheduling message for {phone_number} at {run_date}. Job ID: {job_id}")
    
    scheduler.add_job(
        _send_whatsapp_message_job,
        'date',
        run_date=run_date,
        args=[phone_number, message],
        id=job_id,
        replace_existing=True
    )