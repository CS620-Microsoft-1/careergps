"""Reject request bodies over a size limit before the app reads them.

FastAPI parses a multipart form (spooling it to temp files) before it runs dependencies such as
login, so without this an anonymous client could fill the temp disk with one huge upload.
"""
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _TooLarge(Exception):
    pass


class BodyLimitMiddleware:
    """413 for a declared Content-Length over max_bytes, or once a streamed (chunked) body passes it."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    @staticmethod
    def _reject() -> JSONResponse:
        return JSONResponse(status_code=413, content={"detail": "Request body is too large."})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject()(scope, receive, send)
            return

        received = 0
        exceeded = started = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    exceeded = True
                    raise _TooLarge
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal started
            if exceeded:
                return  # drop whatever the app answers to the cut-off body (e.g. a 400 parse error)
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            # The app may turn the cut-off body into another error; only the size problem matters.
            if not exceeded:
                raise
        if exceeded and not started:
            await self._reject()(scope, receive, send)
