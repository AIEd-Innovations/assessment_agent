"""MongoDB and course-ownership dependencies for the Assessment Agent."""
from __future__ import annotations

from fastapi import HTTPException, Request

from aied_db import Role, guarded
from aied_db.repos import AssessmentRepo
from aied_db.stores import MongoSystemStore

from assessment_agent.auth import Instructor


def database(request: Request):
    """The process-wide database set during application startup."""
    return request.app.state.database


def owner_repo(request: Request, course_id: str, instructor: Instructor | None) -> tuple[AssessmentRepo, str]:
    """Return an instructor-scoped repo after verifying course ownership.

    Local development has no configured Microsoft app and therefore receives an
    anonymous development actor. Production always has an Instructor here.
    """
    db = database(request)
    actor_id = "local_instructor"
    if instructor is not None:
        system = MongoSystemStore(guarded(db, Role.INSTRUCTOR, actor_id=instructor.oid))
        user = system.get_user_by_sso_subject(instructor.oid)
        course = system.get_course(course_id)
        if user is None or course is None or course.get("instructor_id") != user["id"]:
            raise HTTPException(403, "You do not own this course")
        actor_id = user["id"]
    return AssessmentRepo(guarded(db, Role.INSTRUCTOR, actor_id=actor_id), course_id), actor_id


def agent_repo(request: Request, course_id: str) -> AssessmentRepo:
    """The insert-only Assessment Agent view used to persist grading output."""
    return AssessmentRepo(guarded(database(request), Role.ASSESSMENT_AGENT, actor_id="assessment_agent"), course_id)
