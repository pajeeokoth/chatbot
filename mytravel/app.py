import os

from aiohttp import web
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from the .env file located alongside this script
load_dotenv(Path(__file__).with_name(".env"))

# Try to import BotBuilder and the bot. If packages are missing, the server will still
# run but the `/api/messages` endpoint will return 503 with an explanatory message.
BOT_AVAILABLE = False
adapter = None
bot = None
Activity = None
TurnContext = None

try:
    from botbuilder.schema import Activity
    from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
    from bot import TravelBot

    APP_ID = os.getenv("MICROSOFT_APP_ID", "")
    APP_PASSWORD = os.getenv("MICROSOFT_APP_PASSWORD", "")

    adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
    adapter = BotFrameworkAdapter(adapter_settings)

    bot = TravelBot()
    BOT_AVAILABLE = True
except Exception as _err:
    # Missing botbuilder packages or issues importing the bot. Keep the server running
    # so the health endpoint works and so we can install dependencies without a 500 on startup.
    BOT_AVAILABLE = False


async def messages(req: web.Request) -> web.Response:
    # If BotBuilder or the bot implementation is not available, return 503 with a helpful message
    if not BOT_AVAILABLE:
        return web.Response(status=503, text=(
            "Bot Framework packages are not installed in this environment. "
            "Install the project requirements (e.g. python -m pip install -r mytravel/requirements.txt) "
            "or set up a Python environment with the BotBuilder SDK, then restart the server."))

    if req.content_type != "application/json":
        return web.Response(status=415)

    body = await req.json()
    activity = Activity().deserialize(body)

    async def aux_func(turn_context: TurnContext):
        await bot.on_turn(turn_context)

    auth_header = req.headers.get("Authorization", "")

    try:
        await adapter.process_activity(activity, auth_header, aux_func)
        # Return 200 OK to align with Bot Framework Emulator expectations
        return web.Response(status=200)
    except Exception as e:
        return web.Response(text=str(e), status=500)


async def options_messages(req: web.Request) -> web.Response:
    # Support CORS preflight and non-POST clients (return 200 OK)
    headers = {
        "Access-Control-Allow-Origin": req.headers.get("Origin", "*"),
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": req.headers.get("Access-Control-Request-Headers", "Authorization,Content-Type"),
    }
    return web.Response(status=200, headers=headers)

async def serve_index(req: web.Request) -> web.Response:
    """Serve static index.html from /static as the landing page.
    Falls back to a simple text message if the file is missing.
    """
    static_index = Path(__file__).parent / "static" / "index.html"
    if static_index.exists():
        return web.FileResponse(path=str(static_index))
    return web.Response(text="MyTravel bot is running. POST to /api/messages with a Bot Framework Activity.")

# Redefine health with a minimal, plain-text response (remove old HTML block)
async def health(req: web.Request) -> web.Response:
    return web.Response(text="MyTravel bot is running. POST to /api/messages with a Bot Framework Activity.")

# A GET handler for /api/messages that returns a friendly message instead of 405.
async def messages_info(request: web.Request) -> web.Response:
    return web.Response(
        text="POST Bot Framework Activities to this endpoint: /api/messages",
        content_type="text/plain",
        status=200,
    )
app = web.Application()
app.router.add_post("/api/messages", messages)
app.router.add_options("/api/messages", options_messages)
app.router.add_get("/api/messages", messages_info)
app.router.add_get("/health", health)
app.router.add_get("/", serve_index)
if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=3978)

