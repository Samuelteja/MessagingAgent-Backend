# AI Salon Assistant - Full Stack Application

This repository contains the full-stack source code for the AI-powered messaging assistant. The application is built with a Python/FastAPI backend, a React frontend, and communicates with WhatsApp via the WPPConnect server.

## Project Architecture

The application runs as three distinct services:

1.  **FastAPI Backend (`/src`):** Handles all business logic, AI processing, database interactions, and the client-facing API.
2.  **React Frontend (`/frontend`):** The dashboard UI for the salon owner to manage the system.
3.  **WPPConnect Server (Docker):** A separate, third-party service that connects to WhatsApp Web and notifies our backend of new messages via webhooks.

---

## 1. Local Development Setup

Follow these steps to get the full application running on your local machine.

### Prerequisites

*   Python 3.9+
*   Node.js 18+ (for the frontend)
*   [Git](https://git-scm.com/)
*   [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.

---

### Step 1: Clone the Repository & Set Up Backend

```bash
# Clone this repository
git clone <your_repo_url>
cd MessagingAgent

# Create and activate a Python virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install all Python dependencies
pip install -r requirements.txt
Step 2: Configure Environment Variables
In the project root (MessagingAgent/), create a new file named .env.
Copy the contents of .env.example into it and fill in the required values:
GOOGLE_API_KEY: Your API key from Google AI Studio.
WPP_SECRET_KEY: A secure, random string of your choice (e.g., MySuperSecretToken123). This will be used to authorize your backend with the WPPConnect server.
(Note: If you don't have a .env.example file, create one now with placeholder values for your team).
Step 3: Set Up and Run the WPPConnect Server
This project is built against a specific version of WPPConnect to ensure stability. Do not use the latest Docker image.
3.1: (One-Time Setup) Apply Custom Configuration
Our application requires a modified configuration for the WPPConnect server.
Clone the pinned version of the wppconnect-server into the project root.
code
Bash
# This checks out the exact commit we have tested against.
git clone https://github.com/wppconnect-team/wppconnect-server.git
cd wppconnect-server
git checkout afc239b 
cd ..
Overwrite the default config with our custom version from this repository.
From PowerShell:
code
Powershell
Copy-Item -Path "src\config\wppconnect_templates\config.ts" -Destination "wppconnect-server\src\config.ts" -Force
From Git Bash:
code
Bash
cp -f src/config/wppconnect_templates/config.ts wppconnect-server/src/config.ts
Build the local Docker image. This creates a Docker image named custom-wpp-server on your machine that includes our changes.
code
Bash
cd wppconnect-server
docker build . -t custom-wpp-server
cd ..
3.2: Run the Custom WPPConnect Container
Open a separate, dedicated terminal for this service.
code
Bash
# Replace YOUR_SECRET_KEY with the same value from your .env file
docker run --rm -it --name wppconnect-server -p 21465:21465 \
  -e "SECRET_KEY=YOUR_SECRET_KEY" \
  -e "WEBHOOK_URL=http://host.docker.internal:8000/webhook/whatsapp" \
  custom-wpp-server
After running, a QR code will appear. Scan it with the WhatsApp account you wish to use for the bot. Leave this terminal running.
Step 4: Run the FastAPI Backend
Open a second terminal in the project root.
code
Bash
# Make sure your virtual environment is activated
.\venv\Scripts\activate

# Start the server with auto-reload
uvicorn src.main:app --reload
The API will be available at http://127.0.0.1:8000.
Step 5: Run the React Frontend
Open a third terminal.
code
Bash
# Navigate to the frontend directory
cd frontend

# Install dependencies
npm install

# Start the development server
npm start
Your dashboard will be available at http://localhost:3000. The application is now fully running.