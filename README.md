
# MyTravel Bot 
### (aiohttp + Conversational Language Understanding)

This bot runs on aiohttp, uses the Microsoft Bot Framework SDK for Python, and integrates with Azure AI Language — Conversational Language Understanding (CLU). It exposes the Bot Framework endpoint at `/api/messages`.

## Structure
- `extraction_script.py`
- `P10_jupyternotebook.ipynb`
- `mytravel/` — aiohttp bot exposing `/api/messages` (CLU-enabled)


The app runs on `http://localhost:3978` for local development.
# chatbot
chatbot to help users choose a travel offer
This project is to create a chatbot to help users choose a travel offer.
It is part of the OpenClassrooms "Build your own chatbot with Deep Learning" course.
The chatbot will be trained on a dataset of conversations between users and travel agents.
The dataset is in JSON format and contains information about the user's preferences, the travel offers, and the conversation history.
The chatbot will be implemented using Python and the Azure Services.
The project will be divided into the following steps:
1. Load and preprocess the dataset
2. Build and train the chatbot model
3. Evaluate the model
4. Deploy the chatbot
The dataset used in this project is the Frames dataset, which is available on GitHub:



## Prerequisites
- Python 3.9+
- Bot Framework Emulator (for local testing)
- An Azure AI Language resource with a CLU project and a deployed model

## Setup
1. Create a virtualenv and install dependencies:

```bash
python -m venv venv
source venv/Scripts/activate  # Windows Git-bash: source venv/Scripts/activate
python -m pip install -r mytravel/requirements.txt
```

2) Environment variables (create `mytravel/.env`)
Use uppercase names. For local Emulator, leave App ID/Password empty.
```bash
export MICROSOFT_APP_ID=""
export MICROSOFT_APP_PASSWORD=""

# CLU env vars 
CLU_PROJECT_NAME=""
CLU_DEPLOYMENT_NAME=""
CLU_API_KEY=""
CLU_ENDPOINT=""
```

```
# Bot Framework credentials (leave empty for local Emulator)
MICROSOFT_APP_ID=
MICROSOFT_APP_PASSWORD=

# Conversational Language Understanding (CLU)
CLU_PROJECT_NAME=
CLU_DEPLOYMENT_NAME=
CLU_API_KEY=
CLU_ENDPOINT=  # e.g., https://your-resource.cognitiveservices.azure.com
```

Notes:
- `CLU_ENDPOINT` must include `https://` and no trailing slash.
- If CLU variables are not set, the bot falls back to echo so you can keep developing.

## Run
```bash
python mytravel/app.py
```
The server listens on `http://localhost:3978`.

## Test with Emulator
- Endpoint URL: `http://localhost:3978/api/messages`
- Microsoft App ID: leave empty for local
- Microsoft App Password: leave empty for local

Auth rules:
- For local Emulator, leave BOTH MICROSOFT_APP_ID and MICROSOFT_APP_PASSWORD empty in `.env` and in the Emulator.
- For channels or authenticated Emulator connections, set BOTH values and enter the same pair in the Emulator. If only one is set, the app falls back to unauthenticated mode for local development.

## CLU behavior
- With CLU configured, the bot calls CLU and returns a compact JSON summary: top intent, confidence, and entities.
- Without CLU, the bot echoes the user message.
# MyTravel Bot (aiohttp + CLU)

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

Notes:
- This is a minimal example. For production, use proper error handling, HTTPS, and configure channels in Azure Bot Service.
