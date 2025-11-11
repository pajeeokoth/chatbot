"""Minimal TravelBot.

Features:
 - Echo fallback when CLU not configured.
 - Graceful suppression of CLU errors (never raises to caller).
 - Compact intent/entity formatting when CLU succeeds.
"""

import os
import logging
from botbuilder.core import ActivityHandler, TurnContext

try:  # optional CLU import
    from azure.core.credentials import AzureKeyCredential  # type: ignore
    from azure.ai.language.conversations import ConversationAnalysisClient  # type: ignore
except Exception:  # noqa: BLE001
    ConversationAnalysisClient = None  # type: ignore
    AzureKeyCredential = None  # type: ignore


class TravelBot(ActivityHandler):
    def __init__(self) -> None:  # noqa: D401
        super().__init__()
        self._enable_clu()

    def _enable_clu(self) -> None:
        need = ["CLU_PROJECT_NAME", "CLU_DEPLOYMENT_NAME", "CLU_API_KEY", "CLU_ENDPOINT"]
        self.clu_enabled = ConversationAnalysisClient is not None and all(os.getenv(k) for k in need)
        if not self.clu_enabled:
            self._clu_reason = "missing configuration or library"
            return
        endpoint = os.getenv("CLU_ENDPOINT", "")
        if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
            endpoint = "https://" + endpoint
        try:
            self.clu_client = ConversationAnalysisClient(endpoint=endpoint, credential=AzureKeyCredential(os.getenv("CLU_API_KEY")))  # type: ignore[arg-type]
            self.clu_project = os.getenv("CLU_PROJECT_NAME")
            self.clu_deployment = os.getenv("CLU_DEPLOYMENT_NAME")
            self._clu_reason = "enabled"
        except Exception as e:  # noqa: BLE001
            logging.warning("CLU init failed: %s", e)
            self.clu_enabled = False
            self._clu_reason = f"init error: {e}"[:160]

    async def on_message_activity(self, turn_context: TurnContext):  # type: ignore[override]
        text = (turn_context.activity.text or "").strip()
        if not text:
            await turn_context.send_activity("Say something (empty message received).")
            return
        if not self.clu_enabled:
            await turn_context.send_activity(f"(Echo) {text}\nCLU: {self._clu_reason}")
            return
        try:
            task = {
                "kind": "Conversation",
                "analysisInput": {"conversationItem": {"id": "1", "text": text, "modality": "text", "language": "en", "participantId": "user"}},
                "parameters": {"projectName": self.clu_project, "deploymentName": self.clu_deployment, "stringIndexType": "TextElement_V8"},
            }
            result = self.clu_client.analyze_conversation(task)  # type: ignore[attr-defined]
            pred = result["result"]["prediction"]
            top = pred.get("topIntent") or "UNKNOWN"
            intents = pred.get("intents", [])
            conf = next((i.get("confidenceScore") for i in intents if i.get("category") == top), None)
            ents = pred.get("entities", [])
            ent_fmt = ", ".join(f"{e.get('category')}='{e.get('text')}'" for e in ents)
            msg = f"Intent: {top}"
            if conf is not None:
                msg += f" | confidence={conf:.2f}"
            if ent_fmt:
                msg += f" | entities={ent_fmt}"
            await turn_context.send_activity(msg)
        except Exception as e:  # noqa: BLE001
            logging.warning("CLU error (fallback to echo): %s", e)
            await turn_context.send_activity(f"(Echo) {text}\nCLU error: {str(e)[:120]}")