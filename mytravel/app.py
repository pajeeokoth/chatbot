import os
import json
import asyncio

from aiohttp import web
from botbuilder.schema import Activity
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext

from bot import TravelBot


APP_ID = os.getenv("MICROSOFT_APP_ID", "")
APP_PASSWORD = os.getenv("MICROSOFT_APP_PASSWORD", "")

adapter_settings = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(adapter_settings)

bot = TravelBot()


async def messages(req: web.Request) -> web.Response:
    if req.content_type != "application/json":
        return web.Response(status=415)

    body = await req.json()
    activity = Activity().deserialize(body)

    async def aux_func(turn_context: TurnContext):
        await bot.on_turn(turn_context)

    auth_header = req.headers.get("Authorization", "")

    try:
        await adapter.process_activity(activity, auth_header, aux_func)
        return web.Response(status=201)
    except Exception as e:
        return web.Response(text=str(e), status=500)


def main() -> None:
    port = int(os.getenv("PORT", 3978))
    app = web.Application()
    app.router.add_post("/api/messages", messages)
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
