"""Authenticate one v9 read-only conversation turn."""
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.deps import get_current_user
from app.core.config import BACKEND_ROOT, CopilotSettings
from app.core.security import AuthenticatedUser
from app.schemas.copilot import CopilotCapabilities, CopilotReply, CopilotRequest
from app.services.copilot.agent import ChatContext, CopilotError, FoundryCopilotService
from app.services.copilot.readonly import ReadOnlyResumeSource
from app.services.copilot.reports import ReadOnlyReportSource

router = APIRouter(prefix="/copilot", tags=["copilot"])


def get_copilot_service() -> FoundryCopilotService:
    return FoundryCopilotService(CopilotSettings())


def start_copilot_turn() -> float:
    return monotonic()


def get_readonly_report_source() -> ReadOnlyReportSource:
    return ReadOnlyReportSource(BACKEND_ROOT / "local_results" / "web_skill_gaps")


def get_readonly_resume_source() -> ReadOnlyResumeSource:
    from app.db.session import SessionLocal

    return ReadOnlyResumeSource(SessionLocal)


@router.get("/capabilities", response_model=CopilotCapabilities)
def capabilities(user: AuthenticatedUser = Depends(get_current_user)) -> CopilotCapabilities:
    settings = CopilotSettings()
    return CopilotCapabilities(dataReadsEnabled=settings.copilot_readonly_enabled and settings.is_configured)


@router.post("/chat", response_model=CopilotReply)
def chat(request: CopilotRequest, response: Response, started_at: float = Depends(start_copilot_turn),
         user: AuthenticatedUser = Depends(get_current_user),
         resumes: ReadOnlyResumeSource = Depends(get_readonly_resume_source),
         reports: ReadOnlyReportSource = Depends(get_readonly_report_source),
         service: FoundryCopilotService = Depends(get_copilot_service)) -> CopilotReply:
    try:
        resumes.require_account(user.id)
        response.headers["Cache-Control"] = "no-store"
        return service.chat(request, ChatContext(user_id=user.id, resumes=resumes, reports=reports,
                                               job_family=request.jobFamily),
                            started_at=started_at)
    except CopilotError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from None
