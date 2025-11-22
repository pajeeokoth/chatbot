"""Slim aiohttp host for MyTravel Bot (CLU + Bot Framework)."""

import os, sys, logging, traceback, json
from urllib.parse import urlparse
from aiohttp import web
from pathlib import Path
from dotenv import load_dotenv
from collections import deque
from datetime import datetime

# Load environment variables
DOTENV_PATH = Path(__file__).with_name(".env")
_DOTENV_EXISTS = DOTENV_PATH.exists()
load_dotenv(DOTENV_PATH, override=True)

# In-memory error log buffer
ERROR_LOG_BUFFER = deque(maxlen=50)

# -----------------------------
# environment processing functions 
# _normalize_env_aliases, _postprocess_env, _clu_config_warnings, _mask
# -----------------------------

def _normalize_env_aliases() -> None:
    """Normalize lowercase env var aliases to uppercase."""
    for primary, alt in [
        ("MICROSOFT_APP_ID", "microsoft_app_id"),
        ("MICROSOFT_APP_PASSWORD", "microsoft_app_password"),
        ("CLU_PROJECT_NAME", "clu_project_name"),
        ("CLU_DEPLOYMENT_NAME", "clu_deployment_name"),
        ("CLU_API_KEY", "clu_api_key"),
        ("CLU_ENDPOINT", "clu_endpoint"),
    ]:
        if not os.getenv(primary) and os.getenv(alt):
            os.environ[primary] = os.getenv(alt, "")
    
    # Strip trailing slashes and extract hostname from CLU_ENDPOINT
    host = (os.getenv("CLU_ENDPOINT") or "").strip().rstrip("/")
    if host:
        parsed = urlparse(host)
        if parsed.scheme and parsed.netloc:
            host = parsed.netloc
        os.environ["CLU_ENDPOINT"] = host


def _strip_quotes(val: str | None) -> str | None:
    """Remove surrounding quotes from string."""
    if not val:
        return val
    s = val.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


def _postprocess_env() -> None:
    """Strip quotes and normalize CLU endpoint."""
    for k in ["MICROSOFT_APP_ID", "MICROSOFT_APP_PASSWORD", "CLU_PROJECT_NAME", 
              "CLU_DEPLOYMENT_NAME", "CLU_API_KEY", "CLU_ENDPOINT"]:
        v = os.getenv(k)
        if v is not None:
            os.environ[k] = _strip_quotes(v) or ""
    
    # Add https:// prefix to CLU_ENDPOINT if missing
    ep = (os.getenv("CLU_ENDPOINT") or "").strip().rstrip("/")
    if ep and not ep.startswith(("http://", "https://")):
        ep = "https://" + ep
    if ep:
        os.environ["CLU_ENDPOINT"] = ep


def _clu_config_warnings() -> list[str]:
    """Return warnings for likely CLU misconfiguration."""
    warnings = []
    endpoint = (os.getenv("CLU_ENDPOINT") or "").lower()
    key = os.getenv("CLU_API_KEY") or ""

    if not endpoint:
        warnings.append("CLU_ENDPOINT is empty.")
    elif "cognitiveservices.azure.com" not in endpoint and "api.cognitive.microsoft.com" not in endpoint:
        warnings.append("CLU_ENDPOINT doesn't look like an Azure AI Language endpoint.")
    elif any(bad in endpoint for bad in ("/luis", "/text/analytics", "/qnamaker")):
        warnings.append("CLU_ENDPOINT contains service path. Use only the resource host.")
    elif endpoint.startswith("http://"):
        warnings.append("CLU_ENDPOINT is http://; use https://")

    if not os.getenv("CLU_PROJECT_NAME"):
        warnings.append("CLU_PROJECT_NAME is empty.")
    if not os.getenv("CLU_DEPLOYMENT_NAME"):
        warnings.append("CLU_DEPLOYMENT_NAME is empty.")
    if key and len(key.strip()) < 16:
        warnings.append("CLU_API_KEY looks too short.")

    return warnings


def _mask(value: str | None) -> str:
    """Mask sensitive values for logging."""
    if value is None:
        return "None"
    if value == "":
        return ""
    if len(value) <= 4:
        return "****"
    return value[:2] + "****" + value[-2:]

# ----------------------------
# Initialize environment
# ----------------------------
_normalize_env_aliases()
_postprocess_env()

# -----------------------------------
# Initialize Bot Framework components
# -----------------------------------
BOT_AVAILABLE = False
AUTH_ENABLED = False
_IMPORT_ERROR = ""
adapter = bot = Activity = TurnContext = None

try:
    from botbuilder.schema import Activity, ChannelAccount, ConversationAccount
    from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
    from bot import TravelBot
    
    APP_ID = os.getenv("MICROSOFT_APP_ID", "")
    APP_PASSWORD = os.getenv("MICROSOFT_APP_PASSWORD", "")
    
    # Both or neither required for auth
    if bool(APP_ID) ^ bool(APP_PASSWORD):
        logging.warning("Provide BOTH MICROSOFT_APP_ID and MICROSOFT_APP_PASSWORD for auth; using unauthenticated mode.")
        APP_ID = APP_PASSWORD = ""
    
    adapter = BotFrameworkAdapter(BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD))
    AUTH_ENABLED = bool(APP_ID and APP_PASSWORD)
    bot = TravelBot()
    BOT_AVAILABLE = True
except Exception:
    _IMPORT_ERROR = traceback.format_exc()
    logging.error("Bot initialization failed:\n%s", _IMPORT_ERROR)

# ----------------------------------------------------
# Define all handlers
# serve_index, handle_messages, health, 
# diagnostics, routes_info, logs_info, 
# debug_clu, serve_favicon, catch_all, log_middleware
# ----------------------------------------------------

async def handle_messages(request: web.Request) -> web.Response:
    """Handle Bot Framework messages endpoint."""
    if request.method == "GET":
        return web.Response(text="Bot endpoint. Send POST Bot Framework activities to /api/messages")
    if request.method == "OPTIONS":
        return web.Response(status=200)
    if request.method != "POST":
        return web.Response(text="Use POST with application/json to send a Bot Framework Activity.")

    global BOT_AVAILABLE, bot, adapter
    if not BOT_AVAILABLE:
        msg = ["Bot unavailable (imports failed).", "Install: pip install -r mytravel/requirements.txt", "Check /diagnostics for details."]
        if _IMPORT_ERROR:
            msg.append("Error:\n" + _IMPORT_ERROR[-800:])
        return web.Response(text="\n".join(msg))

    # Parse request body
    body = None
    raw_text = None
    
    if (request.content_type or "").lower().startswith("application/json"):
        try:
            body = await request.json()
        except Exception as e:
            logging.info("JSON parse failed: %s", e)
    
    if body is None:
        try:
            raw_text = await request.text()
        except Exception:
            raw_text = ""

    # Construct valid Activity
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

    try:
        activity = Activity().deserialize(body)
    except Exception as e:
        logging.warning("Activity deserialization failed: %s", e)
        return web.Response(status=200, text=f"Could not parse activity: {str(e)[:100]}")
    # from .adapter import adapter, bot, BOT_AVAILABLE, SimpleTurnContext

    # -----------------------------
    # 🔥 DEV TUNNEL SERVICE URL OVERRIDE
    # -----------------------------
    DEV_TUNNEL_URL = os.getenv("DEV_TUNNEL_URL", "https://purple-deer-1234.devtunnels.ms")  # actual tunnel
    activity.service_url = DEV_TUNNEL_URL
    # -----------------------------

    # Process via adapter
    async def aux(turn: TurnContext):
        await bot.on_turn(turn)
    
    try:
        await adapter.process_activity(activity, request.headers.get("Authorization", ""), aux)
        return web.Response(status=200)
    except Exception as e:
        # Fallback: bypass adapter and call bot directly
        logging.warning("Adapter error, using direct handler: %s", e)
        try:
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
            await bot.on_message_activity(ctx)
            reply = "\n".join(ctx._responses) if ctx._responses else "OK"
            return web.Response(status=200, text=reply)
        except Exception as inner:
            logging.exception("Direct bot handler failed: %s", inner)
            return web.Response(status=200, text=f"Bot error: {str(inner)[:150]}")


async def serve_index(request: web.Request) -> web.Response:
    """Serve index.html or fallback text."""
    index_path = Path(__file__).parent / "static" / "index.html"
    if index_path.exists():
        return web.FileResponse(str(index_path))
    return web.Response(text="MyTravel Bot running. POST to /api/messages")


async def health(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.Response(text="OK")


async def diagnostics(request: web.Request) -> web.Response:
    """Show bot configuration and status."""
    env_keys = ["MICROSOFT_APP_ID", "MICROSOFT_APP_PASSWORD", "CLU_PROJECT_NAME", 
                "CLU_DEPLOYMENT_NAME", "CLU_API_KEY", "CLU_ENDPOINT"]
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
        lines.append("IMPORT_ERROR=" + _IMPORT_ERROR[-500:])
    return web.Response(text="\n".join(lines))


async def routes_info(request: web.Request) -> web.Response:
    """List all registered routes."""
    out = ["ROUTES"]
    for r in request.app.router.routes():
        method = getattr(r, "method", "*")
        res = getattr(r, "resource", None)
        path = getattr(res, "canonical", None) if res else None
        if not path and res:
            try:
                path = res.get_info().get("path")
            except Exception:
                path = str(res)
        out.append(f"{method:7} {path}")
    return web.Response(text="\n".join(out))


async def logs_info(request: web.Request) -> web.Response:
    """Show recent errors and warnings."""
    count = int(request.query.get("count", "50"))
    logs = list(ERROR_LOG_BUFFER)[-count:]
    if not logs:
        return web.Response(text="No errors or warnings logged yet.")
    
    lines = [f"Last {len(logs)} error(s)/warning(s):\n"]
    for entry in logs:
        lines.append(f"[{entry['timestamp']}] {entry['level']}")
        lines.append(entry['message'])
        lines.append("-" * 60)
    
    return web.Response(text="\n".join(lines))


async def debug_clu(request: web.Request) -> web.Response:
    """Test CLU endpoint directly without Bot Framework."""
    text = request.query.get("text", "").strip()
    if not text:
        return web.Response(status=400, text="Query param 'text' required, e.g. /debug-clu?text=hello")

    project = os.getenv("CLU_PROJECT_NAME", "")
    deployment = os.getenv("CLU_DEPLOYMENT_NAME", "")
    api_key = os.getenv("CLU_API_KEY", "")
    endpoint = os.getenv("CLU_ENDPOINT", "")
    
    if not all([project, deployment, api_key, endpoint]):
        return web.Response(status=503, text="CLU not configured. Set CLU_* vars in .env")

    try:
        from azure.core.credentials import AzureKeyCredential
        from azure.ai.language.conversations import ConversationAnalysisClient
        
        if not endpoint.startswith(("http://", "https://")):
            endpoint = "https://" + endpoint
            
        client = ConversationAnalysisClient(endpoint=endpoint, credential=AzureKeyCredential(api_key))
        task = {
            "kind": "Conversation",
            "analysisInput": {
                "conversationItem": {"id": "1", "text": text, "modality": "text", "language": "en", "participantId": "user"}
            },
            "parameters": {"projectName": project, "deploymentName": deployment, "stringIndexType": "TextElement_V8"},
        }
        result = client.analyze_conversation(task)
        pred = result["result"]["prediction"]
        top_intent = pred.get("topIntent")
        intents = pred.get("intents", [])
        conf = next((i.get("confidenceScore") for i in intents if i.get("category") == top_intent), None)
        entities = [{"category": e.get("category"), "text": e.get("text")} for e in pred.get("entities", [])]
        
        payload = {"query": text, "topIntent": top_intent, "confidence": conf, "entities": entities}
        return web.Response(text=json.dumps(payload, ensure_ascii=False), content_type="application/json")
    except Exception as e:
        detail = {"error": str(e)}
        try:
            from azure.core.exceptions import HttpResponseError
            if isinstance(e, HttpResponseError) and getattr(e, "response", None):
                resp = e.response
                detail["status_code"] = getattr(resp, "status_code", None)
                headers = getattr(resp, "headers", {}) or {}
                ct = headers.get("content-type") if hasattr(headers, "get") else None
                if ct:
                    detail["content_type"] = ct
        except Exception:
            pass
        
        if "Cannot deserialize content-type" in detail.get("error", ""):
            detail["hint"] = "CLU endpoint may be wrong. Use '<name>.cognitiveservices.azure.com' (no path)."
        
        warns = _clu_config_warnings()
        if warns:
            detail["config_warnings"] = warns
            
        logging.warning("/debug-clu error: %s", detail)
        return web.Response(status=502, text=json.dumps(detail), content_type="application/json")

@web.middleware
async def log_middleware(request: web.Request, handler):
    """Log requests and handle exceptions."""
    logging.info("%s %s", request.method, request.path_qs)
    try:
        resp = await handler(request)
        logging.info("%s -> %s", request.path, resp.status)
        return resp
    except web.HTTPException as http_err:
        if http_err.status == 404:
            logging.info("404 Not Found: %s", request.path_qs)
        else:
            logging.warning("HTTPException %s on %s", http_err.status, request.path_qs)
        raise
    except Exception:
        logging.exception("Unhandled server error")
        raise


class BufferHandler(logging.Handler):
    """Capture warnings and errors in memory."""
    def emit(self, record):
        if record.levelno >= logging.WARNING:
            try:
                ERROR_LOG_BUFFER.append({
                    "timestamp": datetime.now().isoformat(),
                    "level": record.levelname,
                    "message": self.format(record)
                })
            except Exception:
                pass

# -----------------------------
# Configure logging
# -----------------------------
logging.basicConfig(level=logging.INFO)
logging.getLogger().addHandler(BufferHandler())


async def serve_favicon(request: web.Request) -> web.Response:
    """Serve favicon.ico or transparent fallback."""
    icon_path = Path(__file__).parent / "static" / "favicon.ico"
    if icon_path.exists():
        return web.FileResponse(str(icon_path))
    transparent_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\x0cIDAT\x08\xd7c````\x00\x00\x00\x05\x00\x01\x0d\n\x2d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return web.Response(body=transparent_png, content_type="image/x-icon")


async def catch_all(request: web.Request) -> web.Response:
    """Catch-all handler to prevent 404s."""
    if request.method in ("GET", "HEAD"):
        return await serve_index(request)
    return web.Response(text="OK")

# -----------------------------
# App factory
# Create app and register routes
# -----------------------------


def create_app() -> web.Application:
    app = web.Application(middlewares=[log_middleware])
    app.router.add_static("/static/", path=str(Path(__file__).parent / "static"), name="static")
    app.router.add_get("/", serve_index)
    app.router.add_get("/index.html", serve_index)
    app.router.add_get("/favicon.ico", serve_favicon)

    for base in ["/api/messages", "/api/messages/"]:
        app.router.add_route("GET", base, handle_messages)
        app.router.add_route("POST", base, handle_messages)
        app.router.add_route("OPTIONS", base, handle_messages)

    app.router.add_get("/diagnostics", diagnostics)
    app.router.add_get("/routes", routes_info)
    app.router.add_get("/logs", logs_info)
    app.router.add_get("/health", health)
    app.router.add_get("/debug-clu", debug_clu)
    app.router.add_route("*", "/{tail:.*}", catch_all)

    return app


# Default app instance for running via `python mytravel/app.py`
app = create_app()


# -----------------------------
# Run standalone
# -----------------------------
if __name__ == "__main__":
    logging.info("Starting MyTravel Bot on 0.0.0.0:3978")
    web.run_app(app, host="0.0.0.0", port=3978)