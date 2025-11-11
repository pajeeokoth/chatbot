"""Slim aiohttp host for MyTravel Bot (CLU + Bot Framework).

Concise version:
  - POST /api/messages          -> processes Bot Framework activities
  - GET  /api/messages          -> info text (no 405 on browser open)
  - OPTIONS /api/messages       -> CORS / preflight OK
  - Trailing slash variants supported (/api/messages/)
  - /diagnostics, /routes, /health for troubleshooting
  - /                          -> serves static/index.html if present
  - /static/                   -> static assets

Graceful degradation: if bot imports fail, POST returns 503 with guidance.
"""

import os, sys, logging, traceback, json, re
from urllib.parse import urlparse
from aiohttp import web
from pathlib import Path
from dotenv import load_dotenv
from collections import deque
from datetime import datetime

# Load environment variables from the .env file located alongside this script
DOTENV_PATH = Path(__file__).with_name(".env")
_DOTENV_EXISTS = DOTENV_PATH.exists()
# Override=True so values from .env replace any empty or pre-set shell values
# (useful if you previously exported empty strings in your shell)
load_dotenv(DOTENV_PATH, override=True)

###############################################################################
# Environment loading & normalization
###############################################################################

# In-memory error log buffer (last 50 errors)
ERROR_LOG_BUFFER = deque(maxlen=50)

def _normalize_env_aliases() -> None:
    alias_pairs = [
        ("MICROSOFT_APP_ID", "microsoft_app_id"),
        ("MICROSOFT_APP_PASSWORD", "microsoft_app_password"),
        ("CLU_PROJECT_NAME", "clu_project_name"),
        ("CLU_DEPLOYMENT_NAME", "clu_deployment_name"),
        ("CLU_API_KEY", "clu_api_key"),
        ("CLU_ENDPOINT", "clu_endpoint"),
    ]
    for primary, alt in alias_pairs:
        if not os.getenv(primary) and os.getenv(alt):
            os.environ[primary] = os.getenv(alt, "")
    host = (os.getenv("CLU_ENDPOINT") or "").strip()
    if host:
        while host.endswith("/"):
            host = host[:-1]
        parsed = urlparse(host)
        if parsed.scheme and parsed.netloc:
            host = parsed.netloc
        os.environ["CLU_ENDPOINT"] = host


_normalize_env_aliases()


def _strip_quotes(val: str | None) -> str | None:
    if val is None:
        return None
    s = val.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


def _postprocess_env() -> None:
    keys = [
        "MICROSOFT_APP_ID",
        "MICROSOFT_APP_PASSWORD",
        "CLU_PROJECT_NAME",
        "CLU_DEPLOYMENT_NAME",
        "CLU_API_KEY",
        "CLU_ENDPOINT",
    ]
    for k in keys:
        v = os.getenv(k)
        if v is not None:
            os.environ[k] = _strip_quotes(v) or ""
    ep = (os.getenv("CLU_ENDPOINT") or "").strip()
    if ep:
        while ep.endswith("/"):
            ep = ep[:-1]
        if not ep.startswith("http://") and not ep.startswith("https://"):
            ep = "https://" + ep
        os.environ["CLU_ENDPOINT"] = ep


def _clu_config_warnings() -> list[str]:
    """Return human-friendly warnings for likely CLU misconfiguration.

    Helps explain errors like "Cannot deserialize content-type: text/plain" which
    often indicate a wrong endpoint host (not an Azure AI Language resource) or
    invalid project/deployment names.
    """
    warnings: list[str] = []
    endpoint = (os.getenv("CLU_ENDPOINT") or "").lower()
    project = os.getenv("CLU_PROJECT_NAME") or ""
    deployment = os.getenv("CLU_DEPLOYMENT_NAME") or ""
    key = os.getenv("CLU_API_KEY") or ""

    if not endpoint:
        warnings.append("CLU_ENDPOINT is empty.")
    else:
        # Accept common Azure Language endpoints
        if not ("cognitiveservices.azure.com" in endpoint or "api.cognitive.microsoft.com" in endpoint):
            warnings.append("CLU_ENDPOINT does not look like an Azure AI Language endpoint (expected *.cognitiveservices.azure.com).")
        if any(bad in endpoint for bad in ("/luis", "/text/analytics", "/qnamaker")):
            warnings.append("CLU_ENDPOINT appears to include a path for another service (e.g., LUIS/Text Analytics). Use only the resource host.")
        if endpoint.startswith("http://"):
            warnings.append("CLU_ENDPOINT is http://; use https://")

    if not project:
        warnings.append("CLU_PROJECT_NAME is empty.")
    if not deployment:
        warnings.append("CLU_DEPLOYMENT_NAME is empty.")

    # Cognitive keys are usually 32+ chars; rough check
    if key and len(key.strip()) < 16:
        warnings.append("CLU_API_KEY looks too short; re-copy from Azure portal → Keys & Endpoint.")

    return warnings


_postprocess_env()


def _present_status(name: str) -> str:
    if name in os.environ:
        return "present-empty" if os.environ.get(name, "") == "" else "present-set"
    return "missing"


def _mask(value: str | None) -> str:
    if value is None:
        return "None"
    if value == "":
        return ""  # empty string
    if len(value) <= 4:
        return "****"
    return value[:2] + "****" + value[-2:]

BOT_AVAILABLE = False
AUTH_ENABLED = False
_IMPORT_ERROR = ""
adapter = bot = Activity = TurnContext = None
try:
    from botbuilder.schema import Activity, ChannelAccount, ConversationAccount  # type: ignore
    from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext  # type: ignore
    from bot import TravelBot  # local bot
    APP_ID = os.getenv("MICROSOFT_APP_ID", "")
    APP_PASSWORD = os.getenv("MICROSOFT_APP_PASSWORD", "")
    if bool(APP_ID) ^ bool(APP_PASSWORD):  # only one provided -> ignore both locally
        logging.warning("Provide BOTH MICROSOFT_APP_ID and MICROSOFT_APP_PASSWORD for auth; using unauthenticated mode.")
    # APP_ID & APP_PASSWORD logic
        APP_ID = APP_PASSWORD = ""
    adapter = BotFrameworkAdapter(BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD))
    AUTH_ENABLED = bool(APP_ID and APP_PASSWORD)
    bot = TravelBot()
    BOT_AVAILABLE = True
except Exception:  # noqa: BLE001
    _IMPORT_ERROR = traceback.format_exc()
    logging.error("Bot initialization failed:\n%s", _IMPORT_ERROR)


async def handle_messages(request: web.Request) -> web.Response:
    # Never return 404/405/500 here; always respond 200 with guidance when needed.
    if request.method == "GET":
        return web.Response(text="This is the Bot endpoint. Send POST Bot Framework activities to /api/messages", content_type="text/plain")
    if request.method == "OPTIONS":
        return web.Response(status=200)
    # Treat any non-POST as handled
    if request.method != "POST":
        return web.Response(text="Use POST with application/json to send a Bot Framework Activity.", content_type="text/plain")

    if not BOT_AVAILABLE:
        msg = [
            "Bot unavailable (imports failed or not initialized).",
            "Install requirements: python -m pip install -r mytravel/requirements.txt",
            "Check /diagnostics for details.",
        ]
        if _IMPORT_ERROR:
            msg.append("Startup trace (tail):\n" + _IMPORT_ERROR[-800:])
        return web.Response(text="\n".join(msg), content_type="text/plain")

    # Accept even if content-type is wrong; try to parse JSON and otherwise no-op.
    # Parse request body carefully to avoid "Cannot deserialize content-type: text/plain" errors
    body = None
    raw_text = None
    
    # Only attempt JSON parse if content-type is explicitly JSON
    # if "application/json" in (request.content_type or "").lower():
    if (request.content_type or "").lower().startswith("application/json"):
        try:
            body = await request.json()
        except Exception as e:  # noqa: BLE001
            logging.info("JSON parse failed (will use text fallback): %s", e)
    
    # For non-JSON or failed JSON, read as text
    if body is None:
        try:
            raw_text = await request.text()
        except Exception:  # noqa: BLE001
            raw_text = ""

    # Construct a valid Activity dict
    if not isinstance(body, dict) or not body.get("type"):
        msg_text = (raw_text or "").strip() or "(empty)"
        body = {
            "type": "message",
            "id": "auto-generated",
            "serviceUrl": "http://localhost:3978",
            "channelId": "directline",
            "from": {"id": "user", "name": "User"},
            "recipient": {"id": "bot", "name": "Bot"},
            "conversation": {"id": "conversation-id"},
            "text": msg_text,
        }

    # Deserialize into Activity
    try:
        activity = Activity().deserialize(body)  # type: ignore[arg-type]
    except Exception as e:  # noqa: BLE001
        logging.warning("Activity deserialization failed: %s", e)
        return web.Response(status=200, text=f"Could not parse activity: {str(e)[:100]}")

    # Process via adapter
    async def aux(turn: TurnContext):
        await bot.on_turn(turn)
    
    try:
        await adapter.process_activity(activity, request.headers.get("Authorization", ""), aux)
        return web.Response(status=200)
    except Exception as e:  # noqa: BLE001
        # Adapter failed; bypass it and call bot's message handler directly
        logging.warning("Adapter error, using direct message handler: %s", e)
        try:
            # Create a minimal mock TurnContext-like object with just what the bot needs
            class SimpleTurnContext:
                def __init__(self, act):
                    self.activity = act
                    self._responses = []
                async def send_activity(self, text_or_activity):
                    if isinstance(text_or_activity, str):
                        self._responses.append(text_or_activity)
                    else:
                        self._responses.append(getattr(text_or_activity, 'text', str(text_or_activity)))
            
            ctx = SimpleTurnContext(activity)
            await bot.on_message_activity(ctx)  # type: ignore[attr-defined]
            reply = "\n".join(ctx._responses) if ctx._responses else "OK"
            return web.Response(status=200, text=reply, content_type="text/plain")
        except Exception as inner:  # noqa: BLE001
            logging.exception("Direct bot handler also failed: %s", inner)
            return web.Response(status=200, text=f"Bot error: {str(inner)[:150]}", content_type="text/plain")


async def serve_index(request: web.Request) -> web.Response:
    index_path = Path(__file__).parent / "static" / "index.html"
    if index_path.exists():
        return web.FileResponse(str(index_path))
    return web.Response(text="MyTravel Bot running. POST to /api/messages")

async def health(request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def diagnostics(request: web.Request) -> web.Response:
    env_keys = ["MICROSOFT_APP_ID", "MICROSOFT_APP_PASSWORD", "CLU_PROJECT_NAME", "CLU_DEPLOYMENT_NAME", "CLU_API_KEY", "CLU_ENDPOINT"]
    lines = [
        f"BOT_AVAILABLE={BOT_AVAILABLE}",
        f"AUTH_ENABLED={AUTH_ENABLED}",
        f"Python={sys.version.split()[0]}",
        f"CWD={os.getcwd()}",
        f".env_exists={_DOTENV_EXISTS}",
    ]
    for k in env_keys:
        lines.append(f"{k}={_mask(os.getenv(k))}")
    for w in _clu_config_warnings():
        lines.append("WARN=" + w)
    if _IMPORT_ERROR:
        lines.append("IMPORT_ERROR_TAIL=" + _IMPORT_ERROR[-500:])
    return web.Response(text="\n".join(lines), content_type="text/plain")


async def routes_info(request: web.Request) -> web.Response:
    out = ["ROUTES"]
    for r in request.app.router.routes():
        method = getattr(r, "method", "*")
        res = getattr(r, "resource", None)
        path = getattr(res, "canonical", None) if res else None
        if not path and res:
            try:
                path = res.get_info().get("path")
            except Exception:  # noqa: BLE001
                path = str(res)
        out.append(f"{method:7} {path}")
    return web.Response(text="\n".join(out), content_type="text/plain")

async def logs_info(request: web.Request) -> web.Response:
    """Show recent errors and warnings captured in memory."""
    count = int(request.query.get("count", "50"))
    logs = list(ERROR_LOG_BUFFER)[-count:]
    if not logs:
        return web.Response(text="No errors or warnings logged yet.", content_type="text/plain")
    
    # Format for readability
    lines = [f"Last {len(logs)} error(s)/warning(s):\n"]
    for entry in logs:
        lines.append(f"[{entry['timestamp']}] {entry['level']}")
        lines.append(entry['message'])
        lines.append("-" * 60)
    
    return web.Response(text="\n".join(lines), content_type="text/plain")
@web.middleware
async def log_middleware(request: web.Request, handler):
    logging.info("%s %s", request.method, request.path_qs)
    try:
        resp = await handler(request)
        logging.info("%s -> %s", request.path, resp.status)
        return resp
    except web.HTTPException as http_err:  # normal HTTP errors (e.g., 404) shouldn't dump stack traces
        if http_err.status == 404:
            logging.info("404 Not Found: %s", request.path_qs)
        else:
            logging.warning("HTTPException %s on %s", http_err.status, request.path_qs)
        raise
    except Exception:  # noqa: BLE001
        logging.exception("Unhandled server error")
        raise


# Enable INFO logging for quick diagnostics
logging.basicConfig(level=logging.INFO)

# Custom handler to capture errors in memory
class BufferHandler(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.WARNING:
            try:
                msg = self.format(record)
                ERROR_LOG_BUFFER.append({
                    "timestamp": datetime.now().isoformat(),
                    "level": record.levelname,
                    "message": msg
                })
            except Exception:  # noqa: BLE001
                pass

logging.getLogger().addHandler(BufferHandler())

app = web.Application(middlewares=[log_middleware])
app.router.add_static("/static/", path=str(Path(__file__).parent / "static"), name="static")
app.router.add_get("/", serve_index)
app.router.add_get("/index.html", serve_index)  # convenience
# Provide a favicon to avoid noisy 404 errors from browsers.
async def serve_favicon(request: web.Request) -> web.Response:
    # Look for an actual favicon file first
    icon_path = Path(__file__).parent / "static" / "favicon.ico"
    if icon_path.exists():
        return web.FileResponse(str(icon_path))
    # Fallback: return a 1x1 transparent PNG served as .ico for simplicity
    transparent_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\x0cIDAT\x08\xd7c````\x00\x00\x00\x05\x00\x01\x0d\n\x2d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return web.Response(body=transparent_png, content_type="image/x-icon", status=200)
app.router.add_get("/favicon.ico", serve_favicon)
for base in ["/api/messages", "/api/messages/"]:
    app.router.add_route("GET", base, handle_messages)
    app.router.add_route("POST", base, handle_messages)
    app.router.add_route("OPTIONS", base, handle_messages)
app.router.add_get("/diagnostics", diagnostics)
app.router.add_get("/routes", routes_info)
app.router.add_get("/logs", logs_info)
app.router.add_get("/health", health)

# Log routes on startup for easier 404 debugging
async def _log_routes(app: web.Application) -> None:  # pragma: no cover
    lines = ["Routes:"]
    for r in app.router.routes():
        method = getattr(r, "method", "*")
        res = getattr(r, "resource", None)
        path = getattr(res, "canonical", None) if res else None
        if not path and res:
            try:
                path = res.get_info().get("path")
            except Exception:  # noqa: BLE001
                path = str(res)
        lines.append(f"  {method:7} {path}")
    logging.info("\n" + "\n".join(lines))

app.on_startup.append(_log_routes)

# Simple CLU test endpoint for local verification without the Emulator.
async def debug_clu(request: web.Request) -> web.Response:
    text = request.query.get("text", "").strip()
    if not text:
        return web.Response(status=400, text="Query param 'text' is required, e.g. /debug-clu?text=hello")

    # Read CLU configuration
    project = os.getenv("CLU_PROJECT_NAME", "")
    deployment = os.getenv("CLU_DEPLOYMENT_NAME", "")
    api_key = os.getenv("CLU_API_KEY", "")
    endpoint = os.getenv("CLU_ENDPOINT", "")
    if not all([project, deployment, api_key, endpoint]):
        return web.Response(status=503, text="CLU not configured. Set CLU_PROJECT_NAME, CLU_DEPLOYMENT_NAME, CLU_API_KEY, CLU_ENDPOINT in .env")

    try:
        from azure.core.credentials import AzureKeyCredential  # lazy import
        from azure.ai.language.conversations import ConversationAnalysisClient
        # Ensure https:// prefix
        if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
            endpoint = "https://" + endpoint
        client = ConversationAnalysisClient(endpoint=endpoint, credential=AzureKeyCredential(api_key))
        task = {
            "kind": "Conversation",
            "analysisInput": {
                "conversationItem": {
                    "id": "1",
                    "text": text,
                    "modality": "text",
                    "language": "en",
                    "participantId": "user",
                }
            },
            "parameters": {
                "projectName": project,
                "deploymentName": deployment,
                "stringIndexType": "TextElement_V8",
            },
        }
        result = client.analyze_conversation(task)
        pred = result["result"]["prediction"]
        top_intent = pred.get("topIntent")
        intents = pred.get("intents", [])
        conf = None
        for i in intents:
            if i.get("category") == top_intent:
                conf = i.get("confidenceScore")
                break
        entities = [
            {"category": e.get("category"), "text": e.get("text")}
            for e in pred.get("entities", [])
        ]
        payload = {"query": text, "topIntent": top_intent, "confidence": conf, "entities": entities}
        return web.Response(text=json.dumps(payload, ensure_ascii=False), content_type="application/json")
    except Exception as e:  # noqa: BLE001
        # Produce a more actionable error message for common misconfigurations.
        detail = {"error": str(e)}
        try:
            from azure.core.exceptions import HttpResponseError  # type: ignore
            if isinstance(e, HttpResponseError) and getattr(e, "response", None) is not None:
                resp = e.response
                # status_code and headers are commonly available
                detail["status_code"] = getattr(resp, "status_code", None)
                headers = getattr(resp, "headers", {}) or {}
                # Some transports expose a dict-like headers
                ct = None
                try:
                    ct = headers.get("content-type") if hasattr(headers, "get") else None
                except Exception:
                    ct = None
                if ct:
                    detail["content_type"] = ct
        except Exception:
            pass
        # Heuristic for the frequent SDK message
        if "Cannot deserialize content-type" in detail.get("error", ""):
            detail["hint"] = (
                "Your CLU endpoint likely isn't an Azure AI Language endpoint or returned non-JSON. "
                "Ensure CLU_ENDPOINT looks like '<name>.cognitiveservices.azure.com' (no path), and the key/project/deployment are correct."
            )
        # Include warnings to guide fixes
        warns = _clu_config_warnings()
        if warns:
            detail["config_warnings"] = warns
        logging.warning("/debug-clu error detail: %s", detail)
        return web.Response(status=502, text=json.dumps(detail), content_type="application/json")

app.router.add_get("/debug-clu", debug_clu)

# Catch-all: never return 404 — serve index for GET/HEAD; 200 text for others
async def catch_all(request: web.Request) -> web.Response:
    if request.method in ("GET", "HEAD"):
        return await serve_index(request)
    return web.Response(text="OK", content_type="text/plain")

app.router.add_route("*", "/{tail:.*}", catch_all)

if __name__ == "__main__":
    logging.info("Starting MyTravel Bot (concise host) on 0.0.0.0:3978")
    web.run_app(app, host="0.0.0.0", port=3978)

