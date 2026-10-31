"""Run with: uvicorn app.main:app --reload"""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import certifications, health, job_postings, me, resources, resumes, skill_gaps
from app.core.body_limit import BodyLimitMiddleware
from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(title="CareerGPS API", version="0.1.0")

# The largest request body accepted: a 10 MB résumé plus room for the multipart wrapping.
MAX_REQUEST_BYTES = resumes.MAX_UPLOAD_BYTES + 1024 * 1024

# FastAPI reads a multipart form before login runs, so oversized bodies are refused here first.
# Registered before CORSMiddleware so it runs inside it and its 413s carry CORS headers.
app.add_middleware(BodyLimitMiddleware, max_bytes=MAX_REQUEST_BYTES)


# Registered before CORSMiddleware so it runs inside it. Otherwise an unhandled error leaves as a 500
# without CORS headers, the browser blocks it, and the frontend reports "Can't reach CareerGPS".
@app.middleware("http")
async def unhandled_errors_as_json(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

# Only the listed frontend origins may call the API from a browser. Never use "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(me.router)
app.include_router(resumes.router)
app.include_router(job_postings.router)
app.include_router(skill_gaps.router)
app.include_router(resources.router)
app.include_router(certifications.router)
