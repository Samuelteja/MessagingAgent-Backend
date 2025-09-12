# src/models.py
from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime, Time, JSON, Table, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

conversation_tags_association = Table('conversation_tags_association', Base.metadata,
    Column('conversation_id', Integer, ForeignKey('conversations.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id'), primary_key=True)
)

class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(String, unique=True, index=True, nullable=False) # e.g., "919059669663@c.us"
    name = Column(String, nullable=True) # Will store pushname or the name they provide
    is_name_confirmed = Column(Boolean, default=False, nullable=False)
    ai_is_paused_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    conversations = relationship("Conversation", back_populates="contact", cascade="all, delete-orphan")

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    channel = Column(String, index=True)
    contact_db_id = Column(Integer, ForeignKey('contacts.id'), nullable=False)
    contact = relationship("Contact", back_populates="conversations")
    incoming_text = Column(String)
    outgoing_text = Column(String, nullable=True)
    status = Column(String, default="received")
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    outcome = Column(String, default="pending", nullable=False)
    tags = relationship("Tag", secondary=conversation_tags_association, back_populates="conversations")

class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    conversations = relationship("Conversation", secondary=conversation_tags_association, back_populates="tags")

# --- Campaign MODELS ---
class Campaign(Base):
    __tablename__ = "campaigns"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    message_body = Column(Text, nullable=False) # The template, e.g., "Hi {customer_name}!"
    status = Column(String, default="draft", nullable=False) # draft, sending, completed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    recipients = relationship("CampaignRecipient", back_populates="campaign", cascade="all, delete-orphan")

class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey('campaigns.id'), nullable=False)
    contact_id = Column(String, index=True, nullable=False) # The user's phone number ID
    status = Column(String, default="scheduled", nullable=False) # scheduled, sent, failed_too_soon, etc.
    scheduled_time = Column(DateTime(timezone=True), nullable=False)
    safety_check_passed = Column(Boolean, default=False, nullable=False)
    notes = Column(String, nullable=True) # e.g., "Skipped: User had a conversation 2 hours ago"
    content = Column(Text, nullable=True)
    campaign = relationship("Campaign", back_populates="recipients")


class BusinessKnowledge(Base):
    __tablename__ = "business_knowledge"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, index=True, nullable=False) # The type of knowledge, e.g., 'QA', 'MENU', 'UPSELL'
    key = Column(String, nullable=False) # The question or menu item, e.g., "Do you have parking?", "Classic Haircut"
    value = Column(String, nullable=False) # The answer or price/details, e.g., "Yes, we have free parking.", "{"price": 500, "duration": 30}"
    __table_args__ = (UniqueConstraint('type', 'key', name='_type_key_uc'),)

class StaffRoster(Base):
    __tablename__ = "staff_roster"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    specialties = Column(String, nullable=False)
    schedule = Column(JSON, nullable=False) # A JSON string representing the weekly schedule, e.g., '{"Monday": "10:00-18:00", "Tuesday": "10:00-18:00"}'

class BusinessHours(Base):
    __tablename__ = "business_hours"

    id = Column(Integer, primary_key=True, index=True)
    day_of_week = Column(Integer, unique=True, nullable=False) # Day of the week, where 0=Monday, 1=Tuesday, ..., 6=Sunday
    open_time = Column(Time, nullable=True) # Nullable to allow for closed days
    close_time = Column(Time, nullable=True) # Nullable to allow for closed days
    quiet_hours_start = Column(Time, nullable=True)
    quiet_hours_end = Column(Time, nullable=True)

class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(String, index=True, nullable=False)
    task_type = Column(String, index=True, nullable=False) # The type of task, e.g., 'REMINDER', 'FOLLOWUP'
    scheduled_time = Column(DateTime(timezone=True), nullable=False) # The exact time this task should be executed
    status = Column(String, default="pending", nullable=False) # The status of the task, e.g., 'pending', 'sent', 'cancelled'
    content = Column(String, nullable=True) # Optional: Store content for the message, e.g., appointment details

class MenuItem(Base):
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    category = Column(String, nullable=False, index=True)
    price = Column(Float, nullable=False)
    description = Column(Text, nullable=True)

    # This relationship is what was causing the error.
    # We are now explicitly telling it which foreign key to use.
    upsell_rule = relationship(
        "UpsellRule", 
        back_populates="trigger_service", 
        uselist=False, 
        cascade="all, delete-orphan",
        foreign_keys="[UpsellRule.trigger_menu_item_id]" # <-- THIS IS THE FIX
    )

class UpsellRule(Base):
    __tablename__ = "upsell_rules"

    id = Column(Integer, primary_key=True, index=True)
    suggestion_text = Column(Text, nullable=False)
    
    # Foreign key to the service that triggers this upsell
    # We add an index for faster lookups
    trigger_menu_item_id = Column(Integer, ForeignKey("menu_items.id"), unique=True, index=True)
    
    # Foreign key to the service that is being offered as an upsell
    upsell_menu_item_id = Column(Integer, ForeignKey("menu_items.id"))

    # This relationship defines which service triggers the rule.
    trigger_service = relationship("MenuItem", foreign_keys=[trigger_menu_item_id], back_populates="upsell_rule")
    
    # This relationship defines which service is being offered.
    upsold_service = relationship("MenuItem", foreign_keys=[upsell_menu_item_id])
    