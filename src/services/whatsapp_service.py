# src/services/whatsapp_service.py

import os
import requests
from dotenv import load_dotenv

# Load environment variable
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# Configuration for the WPPConnect server
WPP_SERVER_HOST = "http://localhost:21465"
SESSION_NAME = "NERDWHATS_AMERICA" # Use the session name you created
SECRET_KEY = os.getenv("WPP_SECRET_KEY")

# This global variable will hold our authorization token
AUTH_TOKEN = None

def generate_auth_token():
    """
    Generates a new authorization token from the WPPConnect server.
    This must be called before any other API requests.
    """
    global AUTH_TOKEN
    print("Generating new authentication token...")
    
    if not SECRET_KEY:
        print("❌ WPP_SECRET_KEY not found in .env file. Cannot generate token.")
        return

    token_url = f"{WPP_SERVER_HOST}/api/{SESSION_NAME}/{SECRET_KEY}/generate-token"
    
    try:
        response = requests.post(token_url)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        
        data = response.json()
        if data.get("status") == "success" and data.get("token"):
            # The API requires the 'Bearer' prefix for authorization
            AUTH_TOKEN = f"Bearer {data['token']}"
            print("✅ Authentication token generated successfully.")
        else:
            print(f"❌ Failed to get token from response: {data}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Error generating token: {e}")

def set_typing(phone_number: str, state: bool):
    """
    Sets the typing status using the correct '/typing' endpoint.
    :param state: True to start typing, False to stop.
    """
    if not AUTH_TOKEN: return

    typing_url = f"{WPP_SERVER_HOST}/api/{SESSION_NAME}/typing"
    headers = {"Authorization": AUTH_TOKEN, "Content-Type": "application/json"}
    payload = {
        "phone": phone_number,
        "value": state,
        "isGroup": False
    }
    
    action = "START" if state else "STOP"
    print(f"SET TYPING DEBUG (Action: {action}) ---")
    
    try:
        response = requests.post(typing_url, headers=headers, json=payload, timeout=3)
        response.raise_for_status()
        print(f"✅ 'typing' command successful.")
        print(f"   - Server Status Code: {response.status_code}")
        print(f"   - Server Response: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Error sending 'typing' command: {e}")
        if e.response:
            print(f"   - Server Response Body: {e.response.text}")

def send_reply(phone_number: str, message: str):
    """
    Sends a reply message to a given phone number using the WPPConnect API.
    """
    if not AUTH_TOKEN:
        print("❌ Auth token is not available. Cannot send reply.")
        return

    print(f"Sending reply to {phone_number} via API...")
    
    message_url = f"{WPP_SERVER_HOST}/api/{SESSION_NAME}/send-message"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": AUTH_TOKEN
    }
    
    payload = {
        "phone": phone_number,
        "message": message
    }
    
    try:
        response = requests.post(message_url, headers=headers, json=payload)
        response.raise_for_status()
        
        print(f"✅ Reply sent successfully. Server responded: {response.json()}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Error sending reply via API: {e}")
        # If the token expired (401 Unauthorized), we could try regenerating it here.
        if e.response and e.response.status_code == 401:
            print("Token may have expired. Consider regenerating.")

# --- IMPORTANT ---
# Generate the token once when the application starts.
generate_auth_token()