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

def _execute_pending_tasks():
    """
    This is the main job function that runs every minute. It finds and processes
    all due tasks from the scheduled_tasks table.
    """
    # Each job runs in its own thread, so it needs to create its own DB session.
    db = SessionLocal()
    try:
        print(f"⏰ [{datetime.now()}] Running scheduler job: Processing pending tasks...")
        
        # Find all pending tasks where the scheduled time is now or in the past.
        due_tasks = (
            db.query(models.ScheduledTask)
            .filter(
                models.ScheduledTask.status == 'pending',
                models.ScheduledTask.scheduled_time <= datetime.now(timezone.utc)
            )
            .limit(20)
            .all()
        )

        if not due_tasks:
            print("   - No due tasks found.")
            return

        print(f"   - Found {len(due_tasks)} due task(s) to process.")
        
        # This is the fault-tolerant loop we discussed.
        for task in due_tasks:
            try:
                print(f"   -> Processing Task ID: {task.id}, Type: {task.task_type}, Contact: {task.contact_id}")
                
                # For now, we only have the WhatsApp channel.
                # In Week 2, this will be replaced by the unified notification_service.
                whatsapp_service.send_reply(task.contact_id, task.content)
                
                # If sending was successful, update the status.
                task.status = 'sent'
                print(f"      - Successfully sent. Status updated to 'sent'.")

            except Exception as e:
                # If an error occurs (e.g., invalid phone number), mark the task as 'failed'
                # and log the error. This prevents the entire job from crashing.
                print(f"      - ❌ ERROR processing Task ID {task.id}: {e}")
                task.status = 'failed'
            
            # Commit the status change (either 'sent' or 'failed') for each task individually.
            db.commit()

    finally:
        # Always ensure the database session is closed.
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

        scheduler.add_job(
            _execute_pending_tasks,
            'interval',
            minutes=1,
            id='execute_pending_tasks_job',
            replace_existing=True
        )

        atexit.register(lambda: scheduler.shutdown())
        
    except Exception as e:
        print(f"❌ Error starting APScheduler: {e}")
