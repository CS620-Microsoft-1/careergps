"""Suggested action plans for the latest Skill Gap run of a direction (action-plan-agent or the rule plan)."""
from collections.abc import Iterator
import json
import logging
import queue
import threading

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_account_service, get_current_db_user, get_db
from app.api.routes.skill_gaps import _saved_resume
from app.models import User
from app.schemas.action_plans import ActionPlanRequest, ActionPlanSuggestions
from app.schemas.skill_gap_web import SkillGapRun
from app.services.accounts import AccountService
from app.services.action_plans.planner import ActionPlanner, get_action_planner
from app.services.plans import LocalPlanStore, get_plan_store
from app.services.skill_gaps.runs import SkillGapRunManager, get_skill_gap_run_manager
from app.services.skill_gaps.transport import SkillGapConfigurationError
from app.services.student_courses import list_taken

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/action-plans", tags=["action-plans"])
UNAVAILABLE = "Action plans are unavailable"


def _prepare(request: ActionPlanRequest, user: User, db: Session, accounts: AccountService,
             runs: SkillGapRunManager, store: LocalPlanStore) -> tuple[SkillGapRun, set[str], set[str]]:
    """The latest completed run and what the student already finished; HTTP errors otherwise."""
    saved = _saved_resume(user, accounts, request.job_family)
    try:
        run = runs.latest(user_id=saved.user_id, resume_id=saved.resume_id,
                          reviewed_resume=saved.reviewed_resume, job_family=saved.job_family)
    except KeyError:
        raise HTTPException(status_code=404, detail="Run a skill gap analysis for this direction first") from None
    except SkillGapConfigurationError as error:
        raise HTTPException(status_code=503, detail=error.public_message) from None
    except (OSError, ValueError):
        raise HTTPException(status_code=503, detail="Analysis result is unavailable") from None
    if run.status == "failed":
        raise HTTPException(status_code=409, detail="The latest skill gap analysis failed. Run it again")
    if run.status != "completed":
        raise HTTPException(status_code=409, detail="The skill gap analysis has not finished yet")

    # What the student already finished never comes back as a suggestion.
    try:
        taken = {course.course_id for course in list_taken(db, user.id)}
        done = {item["resource_id"] for item in store.items(user.id, request.job_family) if item["status"] == "done"}
    except (SQLAlchemyError, OSError):
        raise HTTPException(status_code=503, detail=UNAVAILABLE) from None
    accounts.end_reads()  # the Agent call can take a while; don't hold a pooled connection
    return run, taken, done


@router.post("/suggestions", response_model=ActionPlanSuggestions)
def suggestions(request: ActionPlanRequest,
                user: User = Depends(get_current_db_user),
                db: Session = Depends(get_db),
                accounts: AccountService = Depends(get_account_service),
                runs: SkillGapRunManager = Depends(get_skill_gap_run_manager),
                store: LocalPlanStore = Depends(get_plan_store),
                planner: ActionPlanner = Depends(get_action_planner),
                ) -> ActionPlanSuggestions:
    run, taken, done = _prepare(request, user, db, accounts, runs, store)
    try:
        return planner.suggest(run, mode=request.mode, university=user.university,
                               taken_course_ids=taken, done_resource_ids=done)
    except OSError:
        raise HTTPException(status_code=503, detail=UNAVAILABLE) from None


def _line(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"


@router.post("/suggestions/stream")
def suggestions_stream(request: ActionPlanRequest,
                       user: User = Depends(get_current_db_user),
                       db: Session = Depends(get_db),
                       accounts: AccountService = Depends(get_account_service),
                       runs: SkillGapRunManager = Depends(get_skill_gap_run_manager),
                       store: LocalPlanStore = Depends(get_plan_store),
                       planner: ActionPlanner = Depends(get_action_planner),
                       ) -> StreamingResponse:
    """Like /suggestions, but streams NDJSON: one {"type": "stage"} line per build stage, then a "result"
    line ({"suggestions": ...}, same body as /suggestions) or an "error" line ({"status", "detail"}).

    Run and storage problems are still plain 404/409/503 responses, checked before streaming starts.
    """
    run, taken, done = _prepare(request, user, db, accounts, runs, store)
    university = user.university
    events: queue.Queue[dict | None] = queue.Queue()

    def work() -> None:
        try:
            result = planner.suggest(run, mode=request.mode, university=university, taken_course_ids=taken,
                                     done_resource_ids=done, on_event=events.put)
            events.put({"type": "result", "suggestions": result.model_dump(mode="json")})
        except OSError:
            events.put({"type": "error", "status": 503, "detail": UNAVAILABLE})
        except Exception as error:
            # Type only: messages can carry plan data.
            logger.error("Action plan stream failed (%s)", type(error).__name__)
            events.put({"type": "error", "status": 500, "detail": "Something went wrong while building your plan."})
        finally:
            events.put(None)

    def lines() -> Iterator[str]:
        # If the student leaves, the thread still finishes and caches an Agent plan for next time.
        threading.Thread(target=work, name="action-plan", daemon=True).start()
        while (event := events.get()) is not None:
            yield _line(event)

    return StreamingResponse(lines(), media_type="application/x-ndjson",
                             # Ask proxies not to buffer, so each line reaches the browser right away.
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
