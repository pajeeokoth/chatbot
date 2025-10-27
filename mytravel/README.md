# MyTravel Bot (aiohttp)

This bot runs on aiohttp and exposes the Bot Framework endpoint at `/api/messages`.

Removed legacy files: `bf_bot.py`, `bf_routes.py`, `server_bf.py`, `requirements.bf.txt`. All instructions below apply to the aiohttp app only.

## Prerequisites
- Python 3.9+
- Bot Framework Emulator (for local testing)

## Setup
1) Install dependencies
```bash
pip install -r mytravel/requirements.txt
```

2) Environment variables (optional for local)
Create `mytravel/.env` and add values as needed. For local Emulator, leave App ID/Password empty.
```
MICROSOFT_APP_ID=
MICROSOFT_APP_PASSWORD=
luis_app_id=
luis_api_key=
luis_api_host_name=
```

## Run
```bash
python mytravel/app.py
```
The server listens on `http://localhost:3978`.

## Test with Emulator
- Endpoint URL: `http://localhost:3978/api/messages`
- Microsoft App ID: leave empty for local
- Microsoft App Password: leave empty for local
# MyTravel Bot (aiohttp + Microsoft Bot Builder SDK for Python)

This is a minimal messaging web application using aiohttp and the Microsoft Bot Builder SDK (Python).

Files:
- `app.py` - aiohttp app exposing `/api/messages` for Bot Framework requests.
- `bot.py` - `TravelBot` implementing `ActivityHandler` with optional LUIS integration.
- `requirements.txt` - Python dependencies.

LUIS integration:

- `LUIS_APP_ID` - your LUIS application ID
- `LUIS_API_KEY` - your LUIS prediction key
- `LUIS_API_HOST_NAME` - the host name for the LUIS prediction endpoint, e.g. `your-resource-name.cognitiveservices.azure.com` or `<region>.api.cognitive.microsoft.com`

If these environment variables are set, the bot will call LUIS for each incoming message and return a JSON response containing the top intent and detected entities. If they are not set the bot falls back to a simple echo behavior.

Quick start:
1. Create a virtualenv and install dependencies:

```bash
python -m venv venv
source venv/Scripts/activate  # Windows Git-bash: source venv/Scripts/activate
python -m pip install -r mytravel/requirements.txt
```

2. Set credentials (for Bot Framework channel) or leave blank for local testing:

```bash
export MICROSOFT_APP_ID=""
export MICROSOFT_APP_PASSWORD=""

# LUIS env vars (optional)
export LUIS_APP_ID=""
export LUIS_API_KEY=""
export LUIS_API_HOST_NAME=""
```

3. Run the app (aiohttp):

```bash
python mytravel/app.py
```

4. Use the Bot Framework Emulator to connect to:
   - URL: http://localhost:3978/api/messages
   - Microsoft App ID/Password: (leave blank if not set)

Notes:
- This is a minimal example. For production, use proper error handling, HTTPS, and configure channels in Azure Bot Service.
