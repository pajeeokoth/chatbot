from azure.core.credentials import AzureKeyCredential
from azure.ai.language.conversations import ConversationAnalysisClient
from botbuilder.core import ActivityHandler, TurnContext

import os

class TravelBot(ActivityHandler):
    def __init__(self):
        self.clu_enabled = all(os.getenv(k) for k in (
            "CLU_PROJECT_NAME", "CLU_DEPLOYMENT_NAME", "CLU_API_KEY", "CLU_ENDPOINT"
        ))
        if self.clu_enabled:
            self.clu = ConversationAnalysisClient(
                endpoint=f"https://{os.getenv('CLU_ENDPOINT').lstrip('https://')}",
                credential=AzureKeyCredential(os.getenv("CLU_API_KEY"))
            )
            self.project = os.getenv("CLU_PROJECT_NAME")
            self.deployment = os.getenv("CLU_DEPLOYMENT_NAME")

    async def on_message_activity(self, turn_context: TurnContext):
        text = (turn_context.activity.text or "").strip()
        if not text:
            await turn_context.send_activity("Please send some text.")
            return

        if not self.clu_enabled:
            await turn_context.send_activity(f"(Echo) {text}")
            return

        task = {
            "kind": "Conversation",
            "analysisInput": {
                "conversationItem": {
                    "id": "1",
                    "text": text,
                    "modality": "text",
                    "language": "en",
                    "participantId": "user"
                }
            },
            "parameters": {
                "projectName": self.project,
                "deploymentName": self.deployment,
                "stringIndexType": "TextElement_V8"
            }
        }

        try:
            result = self.clu.analyze_conversation(task)
            top_intent = result["result"]["prediction"]["topIntent"]
            intents = result["result"]["prediction"]["intents"]
            entities = result["result"]["prediction"].get("entities", [])
            confidence = next((i["confidenceScore"] for i in intents if i["category"] == top_intent), None)

            # Basic response using CLU
            reply = f"Intent: {top_intent} (confidence={confidence:.2f})"
            if entities:
                ent_parts = [f"{e['category']}='{e['text']}'" for e in entities]
                reply += " | Entities: " + ", ".join(ent_parts)

            await turn_context.send_activity(reply)
        except Exception as e:
            await turn_context.send_activity(f"CLU error: {e}; falling back to echo.")
            await turn_context.send_activity(f"(Echo) {text}")