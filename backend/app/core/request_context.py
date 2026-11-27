"""Give each HTTP request its own context for Agent call records (see app.services.agent_calls)."""
from starlette.types import ASGIApp, Receive, Scope, Send

from app.services import agent_calls


class RequestContextMiddleware:
    """Starts an empty holder per request; get_current_user fills in the user id.

    Pure ASGI, so the holder is set in the same context the endpoint and its thread pool copy from.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = agent_calls.start_request()
        try:
            await self.app(scope, receive, send)
        finally:
            agent_calls.end_request(token)
