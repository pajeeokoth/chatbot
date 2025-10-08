import os
import requests
from typing import Dict, Any

# Lightweight LUIS query helper. This hits the LUIS prediction endpoint
# and returns the top intent and entities in a normalized dict.
# Usage: from mytravel.luis_client import query_luis
# result = query_luis(text, app_id=..., key=..., endpoint=...)


def query_luis(text: str, app_id: str = None, key: str = None, endpoint: str = None) -> Dict[str, Any]:
    """Query LUIS prediction endpoint and return a minimal result structure.

    The result format (example):
    {
      "top_intent": "BookFlight",
      "intents": { ... },
      "entities": {"fromLocation": "Paris", "toLocation": "London", "budget": 500}
    }

    This helper is intentionally small. For robust usage prefer the
    Azure Cognitive Services SDKs.
    """

    app_id = app_id or os.environ.get("LUIS_APP_ID")
    key = key or os.environ.get("LUIS_PREDICTION_KEY")
    endpoint = endpoint or os.environ.get("LUIS_ENDPOINT")

    if not (app_id and key and endpoint):
        return {"error": "LUIS configuration missing", "top_intent": None, "intents": {}, "entities": {}}

    # Build prediction URL (v3.0 is the current stable shape; adapt if needed)
    # Example: {endpoint}/luis/prediction/v3.0/apps/{appId}/slots/production/predict
    url = endpoint.rstrip("/") + f"/luis/prediction/v3.0/apps/{app_id}/slots/production/predict"

    params = {"query": text, "verbose": True, "showAllIntents": True, "log": False}
    headers = {"Ocp-Apim-Subscription-Key": key}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        top_intent = data.get("prediction", {}).get("topIntent")
        intents = data.get("prediction", {}).get("intents", {})
        raw_entities = data.get("prediction", {}).get("entities", {})

        # LUIS v3 may include a $instance block under prediction.entities.$instance
        instance_block = {}
        if isinstance(raw_entities, dict) and "$instance" in raw_entities:
            instance_block = raw_entities.pop("$instance", {})

        def _first_str(val):
            """Return a reasonable first string representation for val."""
            if val is None:
                return None
            if isinstance(val, str):
                return val
            if isinstance(val, (int, float)):
                return str(val)
            if isinstance(val, list):
                for x in val:
                    s = _first_str(x)
                    if s:
                        return s
                return None
            if isinstance(val, dict):
                # common keys
                for k in ("text", "value", "timex", "resolution", "values"):
                    if k in val:
                        return _first_str(val[k])
                # fallback to any nested value
                for v in val.values():
                    s = _first_str(v)
                    if s:
                        return s
            return None

        entities = {}

        # Helper to read either prediction.entities['name'] or $instance['name']
        def _get_entity_text(name):
            # Check core entity value
            if name in raw_entities:
                return _first_str(raw_entities.get(name))
            # Fallback to instance text blocks
            inst = instance_block.get(name)
            if isinstance(inst, list) and len(inst) > 0:
                # instance entries usually have a 'text' key
                return _first_str(inst[0].get("text") if isinstance(inst[0], dict) else inst[0])
            return None

        # Map many possible entity names for origin/destination
        origin_keys = ("fromLocation", "from", "origin", "departure", "departureCity", "geographyV2", "geography")
        dest_keys = ("toLocation", "to", "destination", "arrival", "arrivalCity", "geographyV2", "geography")

        for k in origin_keys:
            v = _get_entity_text(k)
            if v:
                entities["from"] = v
                break

        for k in dest_keys:
            v = _get_entity_text(k)
            if v:
                # avoid overwriting from if same key used
                if not entities.get("to"):
                    entities["to"] = v
                break

        # datetimeV2 handling: gather date/time values
        datetimes = raw_entities.get("datetimeV2") or raw_entities.get("datetime")
        if datetimes:
            try:
                # datetimes often a list of dicts with values list
                if isinstance(datetimes, list):
                    extracted = []
                    for d in datetimes:
                        if isinstance(d, dict):
                            vals = d.get("values") or []
                            if isinstance(vals, list) and len(vals) > 0:
                                v0 = vals[0]
                                val = _first_str(v0.get("value") or v0.get("timex") or v0)
                                if val:
                                    extracted.append(val)
                        else:
                            v = _first_str(d)
                            if v:
                                extracted.append(v)
                    if len(extracted) > 0:
                        entities["depart"] = extracted[0]
                    if len(extracted) > 1:
                        entities["return"] = extracted[1]
                else:
                    # single item
                    v = _first_str(datetimes)
                    if v:
                        entities["depart"] = v
            except Exception:
                pass

        # numeric budget: check many names
        budget_keys = ("number", "budget", "price", "money", "amount")
        for bk in budget_keys:
            if bk in raw_entities:
                n = raw_entities.get(bk)
                try:
                    if isinstance(n, list) and len(n) > 0:
                        entities["budget"] = int(float(_first_str(n[0])))
                    else:
                        entities["budget"] = int(float(_first_str(n)))
                    break
                except Exception:
                    # try $instance numeric text
                    inst = instance_block.get(bk)
                    if isinstance(inst, list) and len(inst) > 0:
                        try:
                            entities["budget"] = int(float(inst[0].get("text")))
                            break
                        except Exception:
                            pass

        # As a final fallback, try to inspect $instance for any label containing numbers or city-like text
        if not entities.get("from") or not entities.get("to"):
            for name, items in instance_block.items():
                if not isinstance(items, list) or len(items) == 0:
                    continue
                text0 = _first_str(items[0].get("text") if isinstance(items[0], dict) else items[0])
                if text0 and not entities.get("from"):
                    # simple heuristic: if token contains known separators like 'to' it's not reliable; skip
                    if len(text0) > 1:
                        # If we still don't have from, prefer instance with role 'from'
                        entities.setdefault("from", text0)
                elif text0 and not entities.get("to"):
                    entities.setdefault("to", text0)

        # Flatten single-value lists
        for k, v in list(entities.items()):
            if isinstance(v, list) and len(v) == 1:
                entities[k] = v[0]

        return {"top_intent": top_intent, "intents": intents, "entities": entities}
    except Exception as e:
        return {"error": str(e), "top_intent": None, "intents": {}, "entities": {}}
