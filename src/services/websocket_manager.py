# src/services/websocket_manager.py

from fastapi import WebSocket
from typing import List, Dict, Any
from pydantic.json import pydantic_encoder
import json

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accepts a new WebSocket connection and adds it to the list."""
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"New WebSocket connection: {websocket.client}. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Removes a WebSocket connection from the list."""
        self.active_connections.remove(websocket)
        print(f"WebSocket disconnected: {websocket.client}. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """
        Broadcasts a JSON message to all connected clients.
        It iterates backwards to safely remove disconnected clients during the broadcast.
        """
        message_json = json.dumps(message, default=pydantic_encoder)
        print(f"Broadcasting message to {len(self.active_connections)} clients: {message_json}")
        # Iterate over a copy of the list to handle disconnections during broadcast
        for connection in self.active_connections[:]:
            try:
                await connection.send_text(message_json)
            except Exception:
                # If sending fails, assume the client disconnected and remove them.
                self.disconnect(connection)

# Create a single, global instance of the manager that the app can use.
manager = ConnectionManager()