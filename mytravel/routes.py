from aiohttp import web
from .app import (
    handle_messages,
    serve_index,
    serve_favicon,
    diagnostics,
    routes_info,
    logs_info,
    health,
    debug_clu,
    catch_all,
)

def setup_routes(app: web.Application) -> None:
    """
    Registers all routes for the MyTravel bot app.
    """
    # --------------------------------
    # Core routes
    # --------------------------------
    app.router.add_get("/", serve_index)
    app.router.add_get("/index.html", serve_index)
    app.router.add_get("/favicon.ico", serve_favicon)

    # -----------------------------
    # Bot Framework endpoint
    # -----------------------------
    for base in ["/api/messages", "/api/messages/"]:
        app.router.add_route("GET", base, handle_messages)
        app.router.add_route("POST", base, handle_messages)
        app.router.add_route("OPTIONS", base, handle_messages)

    # --------------------------------
    # Utility endpoints
    # --------------------------------
    app.router.add_get("/diagnostics", diagnostics)
    app.router.add_get("/routes", routes_info)
    app.router.add_get("/logs", logs_info)
    app.router.add_get("/health", health)
    app.router.add_get("/debug-clu", debug_clu)

    # --------------------------------
    # Catch-all for everything else
    # --------------------------------
    app.router.add_route("*", "/{tail:.*}", catch_all)
