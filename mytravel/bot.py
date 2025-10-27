import os
import json
from typing import Optional
from dotenv import load_dotenv

from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.core import RecognizerResult
from botbuilder.ai.luis import LuisApplication, LuisRecognizer

load_dotenv()  # Load environment variables from .env file if present

class TravelBot(ActivityHandler):
    """A bot that uses LUIS to recognize intents and entities.

    If LUIS environment variables are not provided the bot falls back to an echo response.
    """

    def __init__(self):
        luis_app_id = os.getenv("LUIS_APP_ID", "")
        luis_api_key = os.getenv("LUIS_API_KEY", "")
        luis_api_host_name = os.getenv("LUIS_API_HOST_NAME", "fly")

        self.luis_recognizer: Optional[LuisRecognizer] = None
        if luis_app_id and luis_api_key and luis_api_host_name:
            # host name should be like "<your-resource>.cognitiveservices.azure.com" or "<region>.api.cognitive.microsoft.com"
            luis_endpoint = f"https://fly.cognitiveservices.azure.com/"
            luis_app = LuisApplication(luis_app_id, luis_api_key, luis_endpoint)
            self.luis_recognizer = LuisRecognizer(luis_app)

    async def on_message_activity(self, turn_context: TurnContext):
        text = turn_context.activity.text or ""

        if self.luis_recognizer:
            # Call LUIS recognizer
            recognizer_result: RecognizerResult = await self.luis_recognizer.recognize(turn_context)

            # Determine top intent
            top_intent = LuisRecognizer.top_intent(recognizer_result)
            # top_intent typically returns a string; keep compatibility if tuple-like
            if isinstance(top_intent, tuple):
                intent_name, score = top_intent
            else:
                intent_name = top_intent
                score = None

            # Entities are available in the recognizer result as a dict-like JSON
            entities = getattr(recognizer_result, "entities", {}) or {}

            reply = {
                "text": f"Top intent: {intent_name}" + (f" (score={score:.2f})" if score is not None else ""),
                "entities": entities,
            }

            await turn_context.send_activity(json.dumps(reply))
        else:
            # Fallback: echo
            await turn_context.send_activity(f"You said: {text}")
