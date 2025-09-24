# src/main.py
from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

# --- Core Application Imports ---
from .database import engine, SessionLocal, Base
from .services import scheduler_service
from .services.websocket_manager import manager

# --- Import all the new routers ---
from .routers import (
    contact_router,
    tag_router,
    knowledge_router,
    campaign_router,
    analytics_router,
    webhook_router,
    menu_router,
    profile_router,
    scheduler_router,
    bookings_router,
    test_helpers_router
)

Base.metadata.create_all(bind=engine)

scheduler_service.initialize_scheduler()

app = FastAPI(
    title="AI Messaging Assistant API",
    description="The modular and scalable backend for the AI Messaging Assistant.",
    version="0.4.0",
)

# --- CORS Middleware ---
# Allows our frontend (e.g., http://localhost:3000) to communicate with the backend.
origins = ["http://localhost:5173", "http://localhost:3000", "http://localhost"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Include all API Routers ---
# This is where we plug in all the endpoints from our separated files.
app.include_router(webhook_router.router)
app.include_router(contact_router.router)
app.include_router(tag_router.router)
app.include_router(knowledge_router.router)
app.include_router(campaign_router.router)
app.include_router(analytics_router.router)
app.include_router(menu_router.router)
app.include_router(profile_router.router)
app.include_router(scheduler_router.router)
app.include_router(bookings_router.router)
app.include_router(test_helpers_router.router)

# ==============================================================================
# --- Core App Endpoints (Non-API) ---
# ==============================================================================

# WebSocket Endpoint for Live Dashboard Updates
@app.websocket("/ws/inbox-updates")
async def websocket_endpoint(websocket: WebSocket):
    """Handles the real-time WebSocket connection for the live inbox dashboard."""
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Root Health Check
@app.get("/", tags=["System"], summary="Root Health Check")
def read_root():
    """A simple health check endpoint to confirm the server is running."""
    return {"status": "ok", "message": "Welcome to the AI Messaging Assistant API!"}