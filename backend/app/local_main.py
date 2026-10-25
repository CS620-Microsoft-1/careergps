"""Database-free local preview: uvicorn app.local_main:app --host 127.0.0.1."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.api.routes import resumes, skill_gaps_local
from app.core.config import BACKEND_ROOT


class LocalWebSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")
    local_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3100,http://127.0.0.1:3100"


settings = LocalWebSettings()
origins = [v.strip() for v in settings.local_cors_origins.split(",") if v.strip()]
app = FastAPI(title="CareerGPS Local Preview", version="core-v12")
app.add_middleware(CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])


@app.middleware("http")
async def local_origin_only(request: Request, call_next):
    # CORS controls which responses a browser can read; reject foreign browser
    # submissions before a multipart resume could consume an Agent request.
    if request.method == "POST" and request.headers.get("origin") not in (None, *origins):
        return JSONResponse(status_code=403, content={"detail": "This local preview accepts requests from its local webpage only."})
    return await call_next(request)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "local", "database": "not_used"}


app.include_router(resumes.router)
app.include_router(skill_gaps_local.router)
