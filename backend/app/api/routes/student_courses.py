"""School courses the student has taken: the Taken button on course cards, and résumé suggestions.

Taken courses are hidden from the Resources lists in the browser; skill-gap scores don't change.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_account_service, get_current_db_user, get_db
from app.models import User
from app.schemas.skill_gap_web import JobFamily
from app.schemas.student_courses import ResumeCourseMatches, TakenCourse, TakenCourseList, TakenCourseUpdate
from app.services import student_courses
from app.services.accounts import AccountService
from app.services.resources import resources_for

router = APIRouter(prefix="/me/courses", tags=["courses"])

_UNAVAILABLE = HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Taken courses are unavailable")


@router.get("", response_model=TakenCourseList)
def list_taken_courses(user: User = Depends(get_current_db_user), db: Session = Depends(get_db)) -> TakenCourseList:
    try:
        rows = student_courses.list_taken(db, user.id)
    except SQLAlchemyError:
        raise _UNAVAILABLE from None
    return TakenCourseList(courses=[TakenCourse.model_validate(row) for row in rows])


@router.put("/{course_id}", response_model=TakenCourse)
def mark_course_taken(course_id: str, data: TakenCourseUpdate | None = None,
                      user: User = Depends(get_current_db_user), db: Session = Depends(get_db)) -> TakenCourse:
    """Mark a course taken. Repeating it keeps the first record."""
    source = data.source if data else "manual"
    try:
        return TakenCourse.model_validate(student_courses.mark_taken(db, user.id, course_id, source))
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found") from None
    except SQLAlchemyError:
        db.rollback()
        raise _UNAVAILABLE from None


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def unmark_course_taken(course_id: str, user: User = Depends(get_current_db_user),
                        db: Session = Depends(get_db)) -> None:
    try:
        student_courses.unmark_taken(db, user.id, course_id)
    except SQLAlchemyError:
        db.rollback()
        raise _UNAVAILABLE from None


@router.get("/resume-matches", response_model=ResumeCourseMatches)
def resume_course_matches(job_family: JobFamily, user: User = Depends(get_current_db_user),
                          accounts: AccountService = Depends(get_account_service),
                          db: Session = Depends(get_db)) -> ResumeCourseMatches:
    """Listed courses whose code appears in the role's résumé and that aren't marked taken yet.
    Only a suggestion: nothing is written until the student confirms (PUT for each course)."""
    resume = accounts.get_resume(user, job_family)
    if resume is None:
        return ResumeCourseMatches(course_ids=[])
    try:
        taken = {row.course_id for row in student_courses.list_taken(db, user.id)}
    except SQLAlchemyError:
        raise _UNAVAILABLE from None
    courses = [entry for entry in resources_for(job_family, user.university)
               if entry["type"] == "school_course" and entry["id"] not in taken]
    found = student_courses.match_courses(student_courses.resume_strings(resume.confirmed_data), courses)
    return ResumeCourseMatches(course_ids=[course["id"] for course in found])
