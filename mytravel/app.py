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

import os, sys, logging, traceback
from urllib.parse import urlparse
from aiohttp import web
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from the .env file located alongside this script
DOTENV_PATH = Path(__file__).with_name(".env")
_DOTENV_EXISTS = DOTENV_PATH.exists()
# Override=True so values from .env replace any empty or pre-set shell values
# (useful if you previously exported empty strings in your shell)
load_dotenv(DOTENV_PATH, override=True)

###############################################################################
# Environment loading & normalization
###############################################################################

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
    from botbuilder.schema import Activity  # type: ignore
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
    if request.method == "GET":
        return web.Response(text="POST Bot Framework activities to /api/messages", content_type="text/plain")
    if request.method == "OPTIONS":
        return web.Response(status=200)
    if request.method != "POST":
        return web.Response(status=405, text="Allowed: GET, POST, OPTIONS")
    if not BOT_AVAILABLE:
        msg = [
            "Bot unavailable (imports failed).",
            "Install dependencies: python -m pip install -r mytravel/requirements.txt",
            "See /diagnostics for details.",
        ]
        if _IMPORT_ERROR:
            msg.append("Trace (tail):\n" + _IMPORT_ERROR[-1200:])
        return web.Response(status=503, text="\n".join(msg))
    if request.content_type != "application/json":
        return web.Response(status=415, text="Content-Type must be application/json")
    body = await request.json()
    activity = Activity().deserialize(body)
    async def aux(turn: TurnContext):
        await bot.on_turn(turn)
    try:
        await adapter.process_activity(activity, request.headers.get("Authorization", ""), aux)
    except Exception as e:  # noqa: BLE001
        logging.exception("Error handling activity: %s", e)
        return web.Response(status=500, text=str(e))
    return web.Response(status=200)


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
        out.append(f"{method} {path}")
    return web.Response(text="\n".join(out), content_type="text/plain")
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

if __name__ == "__main__":
    logging.info("Starting MyTravel Bot (concise host) on 0.0.0.0:3978")
    web.run_app(app, host="0.0.0.0", port=3978)

