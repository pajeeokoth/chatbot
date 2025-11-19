import logging
import os
import traceback
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from bot import TravelBot

# -----------------------------------------------------------------------------
# Load Credentials from env
# -----------------------------------------------------------------------------
'''
    Read App ID and Password if using Azure Bot Channel Registration.
    Direct Line Emulator works fine with both empty strings.
    If only one of the two is provided, both are ignored and unauthenticated
    mode is used.
'''

APP_ID = os.getenv("MICROSOFT_APP_ID", "")
APP_PASSWORD = os.getenv("MICROSOFT_APP_PASSWORD", "")

if bool(APP_ID) ^ bool(APP_PASSWORD):
    logging.warning(
        "Provide BOTH MICROSOFT_APP_ID and MICROSOFT_APP_PASSWORD for auth; using unauthenticated mode."
    )
    APP_ID = APP_PASSWORD = ""

# -----------------------------------------------------------------------------
# Initialize adapter and bot
# -----------------------------------------------------------------------------
adapter = BotFrameworkAdapter(BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD))
bot = TravelBot()
AUTH_ENABLED = bool(APP_ID and APP_PASSWORD)
BOT_AVAILABLE = True

# -----------------------------------------------------------------------------
# Capture import errors
# -----------------------------------------------------------------------------
try:
    from botbuilder.schema import Activity
except Exception:
    BOT_AVAILABLE = False
    Activity = None
    import traceback
    logging.error("Bot imports failed:\n%s", traceback.format_exc())

# -----------------------------------------------------------------------------
# Safety Wrapper: Prevent adapter from ever crashing aiohttp
# -----------------------------------------------------------------------------

async def process_activity(activity, auth_header: str):
    """
    Process incoming activity via adapter.
    Can raise exceptions if adapter fails.
    """
    async def aux(turn: TurnContext):
        await bot.on_turn(turn)

    await adapter.process_activity(activity, auth_header, aux)

# -----------------------------------------------------------------------------
# Fallback if adapter fails
# -----------------------------------------------------------------------------
class SimpleTurnContext:
    """Fallback TurnContext to allow bot response without adapter."""

    def __init__(self, activity):
        self.activity = activity
        self._responses = []

    async def send_activity(self, text_or_activity):
        if isinstance(text_or_activity, str):
            self._responses.append(text_or_activity)
        else:
            self._responses.append(getattr(text_or_activity, "text", str(text_or_activity)))

    def get_reply_text(self):
        return "\n".join(self._responses) if self._responses else "OK"
