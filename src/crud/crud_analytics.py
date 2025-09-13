# src/crud.py
import random
import re
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, cast, Date, case
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from .. import models

def get_analytics_summary(db: Session):
    """
    Calculates various statistics for the analytics dashboard.
    This version formats the date as a string directly in the SQL query to avoid type errors.
    """
    # 1. Core KPIs (these are simple counts and are already correct)
    total_conversations = db.query(models.Conversation).count()
    total_bookings_confirmed = db.query(models.Conversation).filter(models.Conversation.outcome == 'booking_confirmed').count()
    total_handoffs = db.query(models.Conversation).filter(models.Conversation.outcome == 'human_handoff').count()
    
    # 2. Query for conversations per day for the last 7 days
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    
    # This is the key fix: We use the database's date formatting function 
    # (strftime for SQLite) to return a string directly from the query.
    # The format '%Y-%m-%d' produces a string like '2025-09-07'.
    conversations_per_day_results = (
        db.query(
            func.strftime('%Y-%m-%d', models.Conversation.timestamp).label("date"),
            func.count(models.Conversation.id).label("count"),
        )
        .filter(models.Conversation.timestamp >= seven_days_ago)
        .group_by(func.strftime('%Y-%m-%d', models.Conversation.timestamp))
        .order_by(func.strftime('%Y-%m-%d', models.Conversation.timestamp))
        .all()
    )
    
    # 3. Query for outcomes breakdown
    outcomes_breakdown_results = (
        db.query(
            models.Conversation.outcome.label("outcome"),
            func.count(models.Conversation.id).label("count"),
        )
        .group_by(models.Conversation.outcome)
        .all()
    )

    # 4. Return the data in the format the Pydantic schema expects.
    # The `._mapping` attribute converts the SQLAlchemy result row into a dict-like object.
    return {
        "total_conversations": total_conversations,
        "total_bookings_confirmed": total_bookings_confirmed,
        "total_handoffs": total_handoffs,
        "conversations_per_day": [dict(row._mapping) for row in conversations_per_day_results],
        "outcomes_breakdown": [dict(row._mapping) for row in outcomes_breakdown_results],
    }

def get_advanced_analytics(db: Session):
    """
    Calculates advanced, revenue-focused analytics for the dashboard.
    """
    # This query joins conversations with menu items to calculate revenue.
    # It requires that the AI is correctly extracting the 'service' entity.
    
    # We need a way to link conversation text to a menu item.
    # This is a complex task. A simple approach is to look for service names
    # in the conversation text of confirmed bookings.
    
    # 1. Get all menu items to create a regex pattern
    menu_items = db.query(models.MenuItem).all()
    if not menu_items:
        return {
            "total_estimated_revenue": 0.0,
            "avg_revenue_per_booking": 0.0,
            "top_booked_services": []
        }
        
    # 2. Get all confirmed booking conversations
    confirmed_bookings = db.query(models.Conversation).filter(
        models.Conversation.outcome == 'booking_confirmed'
    ).all()
    
    service_stats = {}
    total_revenue = 0.0
    
    # 3. Process conversations in Python (more flexible than a giant SQL query)
    for convo in confirmed_bookings:
        # Check both incoming and outgoing text for service names
        full_text = f"{convo.incoming_text} {convo.outgoing_text}".lower()
        
        for item in menu_items:
            # If a menu item's name is found in the conversation text...
            if item.name.lower() in full_text:
                if item.name not in service_stats:
                    service_stats[item.name] = {"count": 0, "revenue": 0.0, "price": item.price}
                
                service_stats[item.name]["count"] += 1
                service_stats[item.name]["revenue"] += item.price
                total_revenue += item.price
                break # Count only the first service found per conversation
                
    # 4. Format the results
    top_services = sorted(
        [
            {"service_name": name, "booking_count": data["count"], "estimated_revenue": data["revenue"]}
            for name, data in service_stats.items()
        ],
        key=lambda x: x["booking_count"],
        reverse=True
    )[:5] # Return top 5
    
    avg_revenue = total_revenue / len(confirmed_bookings) if confirmed_bookings else 0.0
    
    return {
        "total_estimated_revenue": total_revenue,
        "avg_revenue_per_booking": avg_revenue,
        "top_booked_services": top_services,
    }
