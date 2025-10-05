# src/models.py
from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime, Time, JSON, Table, ForeignKey, UniqueConstraint, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
from datetime import timezone

conversation_tags_association = Table('conversation_tags_association', Base.metadata,
    Column('conversation_id', Integer, ForeignKey('conversations.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id'), primary_key=True)
)

contact_tags_association = Table('contact_tags_association', Base.metadata,
    Column('contact_id', Integer, ForeignKey('contacts.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id'), primary_key=True)
)

class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(String, unique=True, index=True, nullable=False) # e.g., "919059669663@c.us"
    name = Column(String, nullable=True) # Will store pushname or the name they provide
    is_name_confirmed = Column(Boolean, default=False, nullable=False)
    ai_is_paused_until = Column(DateTime(timezone=True), nullable=True)
    conversation_state = Column(JSON, nullable=False, server_default='{}')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    conversations = relationship("Conversation", back_populates="contact", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary=contact_tags_association, back_populates="contacts")
    bookings = relationship("Booking", back_populates="contact", cascade="all, delete-orphan")
    role = Column(String, nullable=True, index=True)

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

class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    contacts = relationship("Contact", secondary=contact_tags_association, back_populates="tags")
    rules = relationship("TagRule", back_populates="tag", cascade="all, delete-orphan")

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
    embedding = Column(JSON, nullable=True)
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
    embedding = Column(JSON, nullable=True)
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
    
class BusinessProfile(Base):
    __tablename__ = "business_profile"
    id = Column(Integer, primary_key=True, index=True)
    business_name = Column(String, nullable=False, default="My Business")
    business_description = Column(Text, nullable=True)
    address = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    business_type = Column(String, nullable=False, default="SALON") # Can be 'SALON' or 'GAS_DISTRIBUTOR'

class TagRule(Base):
    """
    Stores the rules that link a keyword to a specific tag in the main 'tags' table.
    This replaces the old ai_interest_tags table for a more robust, unified system.
    """
    __tablename__ = "tag_rules"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String, unique=True, nullable=False, index=True)
    
    # This is the Foreign Key to our single, unified 'tags' table.
    tag_id = Column(Integer, ForeignKey('tags.id'), nullable=False)
    
    # This defines the relationship back to the Tag object.
    tag = relationship("Tag", back_populates="rules")


class Booking(Base):
    """
    Stores a record of a confirmed appointment made by the AI.
    """
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    contact_db_id = Column(Integer, ForeignKey('contacts.id'), nullable=False)
    staff_db_id = Column(Integer, ForeignKey('staff_roster.id'), nullable=True)
    service_id = Column(Integer, ForeignKey('menu_items.id'), nullable=True)
    service_name_text = Column(String, nullable=False)
    booking_datetime = Column(DateTime(timezone=True), nullable=False)
    end_datetime = Column(DateTime(timezone=True), nullable=True) # For calendar view duration
    notes = Column(Text, nullable=True) # Notes from the receptionist
    status = Column(String, default="confirmed", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    source = Column(String, default="ai_booking", nullable=False)
    contact = relationship("Contact", back_populates="bookings")
    staff = relationship("StaffRoster")
    service = relationship("MenuItem")

class DeliveryList(Base):
    __tablename__ = "delivery_lists"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, default=1, nullable=False)
    file_name = Column(String, nullable=True)
    upload_timestamp = Column(DateTime(timezone=True), server_default=func.now())
    delivery_date = Column(Date, nullable=False, index=True)
    status = Column(String, default="processing", nullable=False)
    deliveries = relationship("DailyDelivery", back_populates="delivery_list", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint('business_id', 'delivery_date', name='_business_delivery_date_uc'),)

class DailyDelivery(Base):
    __tablename__ = "daily_deliveries"
    id = Column(Integer, primary_key=True, index=True)
    delivery_list_id = Column(Integer, ForeignKey('delivery_lists.id'), nullable=False)
    customer_phone = Column(String, index=True, nullable=False)
    customer_name = Column(String, nullable=True)
    customer_address = Column(Text, nullable=True)
    status = Column(String, default="pending_reconciliation", nullable=False)
    failure_reason = Column(String, nullable=True)
    reconciliation_timestamp = Column(DateTime(timezone=True), nullable=True)
    delivery_list = relationship("DeliveryList", back_populates="deliveries")
