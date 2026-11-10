"""Authenticated Copilot requests; this phase does not access the application database."""
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.core.config import CopilotSettings
from app.core.security import AuthenticatedUser
from app.schemas.copilot import CopilotReply, CopilotRequest
from app.services.copilot.agent import CopilotError, FoundryCopilotService
from app.services.copilot.tools import ToolContext

router = APIRouter(prefix="/copilot", tags=["copilot"])


def get_copilot_service() -> FoundryCopilotService:
    return FoundryCopilotService(CopilotSettings())


@router.post("/chat", response_model=CopilotReply)
def chat(request: CopilotRequest, user: AuthenticatedUser = Depends(get_current_user),
         service: FoundryCopilotService = Depends(get_copilot_service)) -> CopilotReply:
    try:
        return service.chat(request, ToolContext(user_id=user.id))
    except CopilotError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from None
