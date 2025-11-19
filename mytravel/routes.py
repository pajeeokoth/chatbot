# import json
# import logging
# from aiohttp import web
# from botbuilder.core import ActivityHandler, BotFrameworkAdapter
# from botbuilder.schema import Activity
# from .adapter import adapter  # configured adapter instance
# from .bot import TravelBot #travel_bot   # bot instance


# async def messages_handler(request: web.Request) -> web.Response:
#     """
#     Handles all POST /api/messages requests from DirectLine / Emulator.
#     Uses BotFrameworkAdapter to run bot logic unless it fails,
#     then falls back to a simple echo handler.
#     """
#     try:
#         body = await request.json()
#     except Exception:
#         return web.json_response({"error": "invalid JSON"}, status=400)

#     # Convert raw JSON to Activity object
#     activity = Activity().deserialize(body)

#     # Override service URL if a tunnel is configured
#     tunnel_url = request.app.get("tunnel_url")
#     if tunnel_url:
#         activity.service_url = tunnel_url

#     logging.info(f"Incoming activity: {activity.type} | Text={activity.text}")

#     # The auth header used by BotFrameworkAdapter (Direct Line sends none)
#     auth_header = request.headers.get("Authorization", "")

#     # FIRST TRY: normal adapter processing
#     try:
#         await adapter.process_activity(activity, auth_header, travel_bot.on_turn)
#         return web.Response(status=200, text="OK")
#     except Exception as e:
#         logging.error(f"Adapter crashed, falling back. Reason: {e}")

#         # FALLBACK: manually invoke bot logic with minimal TurnContext wrapper
#         from botbuilder.core import TurnContext

#         class SimpleContext(TurnContext):
#             """Minimal TurnContext fallback for when adapter crashes."""

#             def __init__(self, act: Activity):
#                 # "adapter" is still needed but unused in fallback logic
#                 super().__init__(adapter, act)
#                 self._activities: list[Activity] = []

#             async def send_activity(self, message):
#                 # capture messages locally — tests read these
#                 if isinstance(message, str):
#                     reply = Activity(
#                         type="message",
#                         text=message,
#                         service_url=activity.service_url,
#                         channel_id=activity.channel_id,
#                         conversation=activity.conversation,
#                         recipient=activity.from_property,
#                         from_property=activity.recipient,
#                     )
#                 else:
#                     reply = message

#                 self._activities.append(reply)
#                 return [reply]

#         ctx = SimpleContext(activity)
#         await travel_bot.on_turn(ctx)

#         # return first reply (what tests expect)
#         if ctx._activities:
#             text = ctx._activities[0].text or "OK"
#         else:
#             text = "OK"

#         return web.Response(status=200, text=text)


# def setup_routes(app: web.Application):
#     """Registers HTTP routes."""
#     app.router.add_post("/api/messages", messages_handler)


########################################################################################
# # mytravel/routes.py

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
    # Core routes
    app.router.add_get("/", serve_index)
    app.router.add_get("/index.html", serve_index)
    app.router.add_get("/favicon.ico", serve_favicon)

    # Bot Framework endpoint
    for base in ["/api/messages", "/api/messages/"]:
        app.router.add_route("GET", base, handle_messages)
        app.router.add_route("POST", base, handle_messages)
        app.router.add_route("OPTIONS", base, handle_messages)

    # Utility endpoints
    app.router.add_get("/diagnostics", diagnostics)
    app.router.add_get("/routes", routes_info)
    app.router.add_get("/logs", logs_info)
    app.router.add_get("/health", health)
    app.router.add_get("/debug-clu", debug_clu)

    # Catch-all for everything else
    app.router.add_route("*", "/{tail:.*}", catch_all)
