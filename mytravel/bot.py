"""Simple echo bot extended with a rule-based flight recommendation flow.

This keeps an in-memory conversation state (per conversation id) and extracts
basic slots from user messages (departure, destination, depart/return dates,
budget). When all slots are known, it returns a small set of simulated flight
offers and asks the user to confirm a booking.

This is intentionally lightweight. For production you should use Dialogs,
persistent Storage, and a LUIS/NLU model for entity extraction.
"""

from typing import Dict, Any, List
import re

from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import ChannelAccount


class MyBot(ActivityHandler):
    def __init__(self):
        # In-memory conversation states (reset when the app restarts).
        # Keyed by conversation.id, value is a dict of slots and flags.
        self.conversations: Dict[str, Dict[str, Any]] = {}

    async def on_members_added_activity(
        self,
        members_added: ChannelAccount,
        turn_context: TurnContext,
    ):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity("Hello and welcome! I can help recommend flights. Tell me where you'd like to go.")

    async def on_message_activity(self, turn_context: TurnContext):
        text = (turn_context.activity.text or "").strip()
        conv_id = turn_context.activity.conversation.id

        # Initialize conversation state if new
        state = self.conversations.setdefault(conv_id, {
            "from": None,
            "to": None,
            "depart": None,
            "return": None,
            "budget": None,
            "offers": None,
            "awaiting_confirmation": False,
        })

        # If we are waiting for a confirmation answer, handle that first
        if state.get("awaiting_confirmation"):
            normalized = text.lower()
            if normalized in ("yes", "y", "confirm", "ok", "1", "book"):
                await turn_context.send_activity("Great — booking confirmed (simulated). I'll send you the itinerary shortly.")
                # Clear conversation state after booking
                self.conversations.pop(conv_id, None)
                return
            elif normalized in ("no", "n", "cancel", "2"):
                await turn_context.send_activity("Okay, I won't book. Would you like to see other options or change your search?")
                state["awaiting_confirmation"] = False
                return

        # First try to query LUIS for intents/entities
        try:
            from mytravel.luis_client import query_luis
            from mytravel.config import DefaultConfig

            cfg = DefaultConfig()
            luis_result = query_luis(text, app_id=cfg.LUIS_APP_ID, key=cfg.LUIS_PREDICTION_KEY, endpoint=cfg.LUIS_ENDPOINT)
            if luis_result and not luis_result.get("error"):
                entities = luis_result.get("entities", {})
                # Merge recognized entities into state
                for slot in ("from", "to", "depart", "return", "budget"):
                    if entities.get(slot):
                        state[slot] = entities.get(slot)
        except Exception:
            # If LUIS fails for any reason, fall back to rule-based extraction
            pass

        # Fall back to rule-based extraction for anything still missing
        extracted = self._extract_slots(text)
        for k, v in extracted.items():
            if v and not state.get(k):
                state[k] = v

        missing = [k for k in ("from", "to", "depart", "return", "budget") if not state.get(k)]

        # If any slot missing, ask for it (ask one at a time)
        if missing:
            next_slot = missing[0]
            question = {
                "from": "Where are you departing from?",
                "to": "What's your destination?",
                "depart": "When do you want to depart? (e.g. 2025-12-20 or next Tuesday)",
                "return": "When will you return?",
                "budget": "What's your maximum budget for the total (numbers only, e.g. 500)?",
            }[next_slot]
            await turn_context.send_activity(question)
            return

        # All slots present: produce recommendations
        if not state.get("offers"):
            offers = self._recommend_flights(state)
            state["offers"] = offers

            if not offers:
                await turn_context.send_activity("Sorry — I couldn't find any offers that match your budget. Try increasing your budget or changing dates.")
                return

            # Present offers to the user
            lines = ["I found the following options:"]
            for i, o in enumerate(offers, start=1):
                lines.append(f"{i}. {o['airline']} — ${o['price']} — Depart: {o['depart_time']} — Return: {o['return_time']}")
            lines.append("Reply '1' to book option 1, '2' for option 2, or 'yes' to confirm the best one.")
            await turn_context.send_activity("\n".join(lines))
            state["awaiting_confirmation"] = True
            return

        # Fallback echo
        await turn_context.send_activity(f"I heard: '{text}'. If you'd like to start a new search say 'search' or 'new'.")

    def _extract_slots(self, text: str) -> Dict[str, Any]:
        """Very small rule-based extractor. Returns any discovered slots.

        This is intentionally simple. For better extraction, integrate LUIS or
        another NLU tool.
        """
        text_low = text.lower()
        slots: Dict[str, Any] = {"from": None, "to": None, "depart": None, "return": None, "budget": None}

        # from -> to pattern: "from X to Y"
        m = re.search(r"from\s+(?P<from>[\w\s]+?)\s+to\s+(?P<to>[\w\s]+)", text_low)
        if m:
            slots["from"] = m.group("from").strip()
            slots["to"] = m.group("to").strip()

        # budget: numbers optionally prefixed by $ or €
        m = re.search(r"(?:budget\s*[:=]?\s*|\$|€)?\s*(?P<b>\d{2,6})\b", text_low)
        if m:
            slots["budget"] = int(m.group("b"))

        # depart and return — look for keywords and a following date-like token
        m_dep = re.search(r"depart(?:ing)?(?: on)?\s+(?P<d>[\w\-\d/, ]{3,30})", text_low)
        if m_dep:
            slots["depart"] = m_dep.group("d").strip()

        m_ret = re.search(r"return(?:ing)?(?: on)?\s+(?P<r>[\w\-\d/, ]{3,30})", text_low)
        if m_ret:
            slots["return"] = m_ret.group("r").strip()

        # quick heuristic: if the user typed two city names separated by '-' or 'to', or just 'to'
        if not slots["to"]:
            m = re.search(r"(?P<a>[A-Z][a-z]+)\s+to\s+(?P<b>[A-Z][a-z]+)", text)
            if m:
                slots["from"] = slots.get("from") or m.group("a").strip()
                slots["to"] = slots.get("to") or m.group("b").strip()

        return slots

    def _recommend_flights(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Simulate flight search and return 3 offers based on budget."""
        budget = state.get("budget") or 0
        base_price = max(50, int(budget * 0.6)) if budget else 200
        offers: List[Dict[str, Any]] = []
        # Create three sample offers with different prices
        for i, mult in enumerate((0.9, 1.0, 1.2), start=1):
            price = int(base_price * mult)
            if budget and price > budget:
                # still include offers slightly above budget as alternatives
                pass
            offers.append(
                {
                    "airline": f"Contoso Air {i}",
                    "price": price,
                    "depart_time": state.get("depart") or "TBD",
                    "return_time": state.get("return") or "TBD",
                }
            )

        # Filter to reasonably priced offers (allow up to 150% of budget)
        if budget:
            offers = [o for o in offers if o["price"] <= max(budget * 1.5, o["price"])]

        return offers


__all__ = ["MyBot"]