"""
Unit tests for the resume generator.

Covers: resolve_plan_items context building, generate_resume LLM call,
DB persistence, error handling, and the anti-hallucination invariant.
"""

import asyncio
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.llm.mock_client import MockLLMClient
from src.models.achievement import Achievement
from src.models.education import Education
from src.models.job import Job
from src.models.project import Project
from src.models.tailoring import PlanItem, PlanItemType, TailoringSession, TailoringStatus
from src.tailor.generator import generate_resume, resolve_plan_items

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_session_with_plan(db) -> TailoringSession:
    job = Job(
        title="Staff Engineer",
        company="Widgets Inc",
        location="Remote",
        start_date=date(2021, 1, 1),
        employment_type="full_time",
        summary="Platform engineering at scale.",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    ach = Achievement(
        job_id=job.id,
        text="Scaled the API gateway to 500M requests per day",
        metric="reduced latency by 40%",
    )
    db.add(ach)

    proj = Project(
        name="Bespoke",
        summary="Resume tailoring tool",
        description="LLM-powered resume tailor using FastAPI and HTMX.",
    )
    db.add(proj)

    edu = Education(
        institution="UC Berkeley",
        degree="B.S.",
        field="Computer Science",
        end_date=date(2016, 5, 1),
    )
    db.add(edu)
    db.commit()
    db.refresh(ach)
    db.refresh(proj)
    db.refresh(edu)

    session = TailoringSession(
        job_title="Senior Engineer",
        company_name="Acme Corp",
        job_description="Build scalable systems.",
        status=TailoringStatus.PLAN_EDITED,
        analysis_json={
            "required_skills": ["Python"],
            "preferred_skills": [],
            "role_level": "senior",
            "domain": "backend",
            "tone": "startup-casual",
            "impact_signals": ["scale"],
            "red_flags": [],
            "emphasis_guidance": "Focus on scale.",
        },
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    items = [
        PlanItem(
            session_id=session.id,
            item_type=PlanItemType.JOB,
            reference_id=job.id,
            include=True,
            sort_order=0,
        ),
        PlanItem(
            session_id=session.id,
            item_type=PlanItemType.ACHIEVEMENT,
            reference_id=ach.id,
            include=True,
            sort_order=1,
        ),
        PlanItem(
            session_id=session.id,
            item_type=PlanItemType.SKILL_GROUP,
            reference_id=None,
            include=True,
            emphasis_note="Python, FastAPI, Docker",
            sort_order=2,
        ),
        PlanItem(
            session_id=session.id,
            item_type=PlanItemType.PROJECT,
            reference_id=proj.id,
            include=True,
            sort_order=3,
        ),
        PlanItem(
            session_id=session.id,
            item_type=PlanItemType.EDUCATION,
            reference_id=edu.id,
            include=True,
            sort_order=4,
        ),
    ]
    db.add_all(items)
    db.commit()
    db.refresh(session)

    return session


def load_session_with_items(db, session_id: int) -> TailoringSession:
    return db.scalar(
        select(TailoringSession)
        .where(TailoringSession.id == session_id)
        .options(selectinload(TailoringSession.plan_items))
    )


# ---------------------------------------------------------------------------
# resolve_plan_items
# ---------------------------------------------------------------------------


def test_resolve_includes_job_and_achievements(db_session):
    session = make_session_with_plan(db_session)
    session = load_session_with_items(db_session, session.id)

    ctx = resolve_plan_items(session, db_session)

    assert len(ctx["experiences"]) == 1
    exp = ctx["experiences"][0]
    assert exp["job"]["company"] == "Widgets Inc"
    assert len(exp["selected_achievements"]) == 1
    assert (
        exp["selected_achievements"][0]["text"] == "Scaled the API gateway to 500M requests per day"
    )


def test_resolve_excludes_deselected_achievement(db_session):
    session = make_session_with_plan(db_session)

    ach_item = next(i for i in session.plan_items if i.item_type == PlanItemType.ACHIEVEMENT)
    ach_item.include = False
    db_session.commit()

    session = load_session_with_items(db_session, session.id)
    ctx = resolve_plan_items(session, db_session)

    assert ctx["experiences"][0]["selected_achievements"] == []


def test_resolve_skill_group_uses_emphasis_note(db_session):
    session = make_session_with_plan(db_session)
    session = load_session_with_items(db_session, session.id)

    ctx = resolve_plan_items(session, db_session)

    assert ctx["skill_group"]["skills"] == "Python, FastAPI, Docker"


def test_resolve_includes_project(db_session):
    session = make_session_with_plan(db_session)
    session = load_session_with_items(db_session, session.id)

    ctx = resolve_plan_items(session, db_session)

    assert len(ctx["projects"]) == 1
    assert ctx["projects"][0]["name"] == "Bespoke"


def test_resolve_includes_education(db_session):
    session = make_session_with_plan(db_session)
    session = load_session_with_items(db_session, session.id)

    ctx = resolve_plan_items(session, db_session)

    assert len(ctx["education"]) == 1
    assert ctx["education"][0]["institution"] == "UC Berkeley"


def test_anti_hallucination_metric_in_context(db_session):
    """All metrics passed to the LLM must come from DB records."""
    session = make_session_with_plan(db_session)
    session = load_session_with_items(db_session, session.id)

    ctx = resolve_plan_items(session, db_session)

    all_metrics = [
        ach.get("metric", "")
        for exp in ctx["experiences"]
        for ach in exp.get("selected_achievements", [])
    ]
    assert "reduced latency by 40%" in all_metrics


# ---------------------------------------------------------------------------
# generate_resume
# ---------------------------------------------------------------------------


def test_generate_returns_required_fields(db_session):
    session = make_session_with_plan(db_session)

    result = asyncio.run(generate_resume(session.id, db_session, MockLLMClient()))

    assert "summary" in result
    assert "experience" in result
    assert "skills" in result
    assert "projects" in result
    assert "education" in result


def test_generate_stores_on_session(db_session):
    session = make_session_with_plan(db_session)

    asyncio.run(generate_resume(session.id, db_session, MockLLMClient()))

    db_session.refresh(session)
    assert session.generated_json is not None
    assert session.generation_prompt_version is not None


def test_generate_bad_json_raises(db_session):
    class BadJSONClient:
        async def chat(self, **kwargs):
            return "this is not json at all"

        async def close(self):
            pass

    session = make_session_with_plan(db_session)

    with pytest.raises(ValueError):
        asyncio.run(generate_resume(session.id, db_session, BadJSONClient()))


def test_generate_missing_session_raises(db_session):
    with pytest.raises(ValueError, match="not found"):
        asyncio.run(generate_resume(99999, db_session, MockLLMClient()))


def test_generate_fenced_json_parses(db_session):
    from pathlib import Path

    fixture = (Path(__file__).parent / "fixtures" / "sample_generation.json").read_text()

    class FencedClient:
        async def chat(self, **kwargs):
            return f"```json\n{fixture}\n```"

        async def close(self):
            pass

    session = make_session_with_plan(db_session)
    result = asyncio.run(generate_resume(session.id, db_session, FencedClient()))
    assert "summary" in result
