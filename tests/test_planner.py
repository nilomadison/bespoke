import asyncio
from datetime import date

import pytest

from src.llm.mock_client import MockLLMClient
from src.models.education import Education
from src.models.job import Job
from src.models.project import Project
from src.models.tailoring import PlanItem, TailoringSession, TailoringStatus
from src.tailor.analyzer import JobAnalysis
from src.tailor.planner import build_plan, serialize_career


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_session(db) -> TailoringSession:
    s = TailoringSession(
        job_title="Senior Engineer",
        company_name="Acme",
        job_description="Build things.",
        status=TailoringStatus.ANALYZING,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def make_job(db) -> Job:
    j = Job(
        title="Engineer",
        company="Corp",
        start_date=date(2020, 1, 1),
    )
    db.add(j)
    db.commit()
    db.refresh(j)
    return j


def make_education(db) -> Education:
    e = Education(
        institution="State U",
        degree="B.S.",
        field="Computer Science",
        end_date=date(2019, 5, 1),
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def make_project(db) -> Project:
    p = Project(name="Side Project", prominence=4)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


DUMMY_ANALYSIS = JobAnalysis(
    required_skills=["Python"],
    role_level="senior",
    domain="backend",
    tone="startup-casual",
)

# ---------------------------------------------------------------------------
# serialize_career
# ---------------------------------------------------------------------------

def test_serialize_career_empty_db(db_session):
    result = serialize_career(db_session)
    assert result["jobs"] == []
    assert result["skills"] == []
    assert result["projects"] == []
    assert result["education"] == []
    assert result["certifications"] == []


def test_serialize_career_with_job(db_session):
    make_job(db_session)
    result = serialize_career(db_session)
    assert len(result["jobs"]) == 1
    assert result["jobs"][0]["company"] == "Corp"


def test_serialize_career_with_education(db_session):
    make_education(db_session)
    result = serialize_career(db_session)
    assert len(result["education"]) == 1
    assert result["education"][0]["institution"] == "State U"


# ---------------------------------------------------------------------------
# build_plan
# ---------------------------------------------------------------------------

def test_build_plan_returns_plan_items(db_session):
    # The mock fixture (sample_plan.json) has 6 items.
    # We don't need real DB rows because plan items use soft FKs.
    session = make_session(db_session)
    client = MockLLMClient()

    items = asyncio.run(build_plan(session.id, DUMMY_ANALYSIS, db_session, client))

    assert len(items) == 6
    assert all(isinstance(i, PlanItem) for i in items)


def test_build_plan_persists_to_db(db_session):
    session = make_session(db_session)
    client = MockLLMClient()

    asyncio.run(build_plan(session.id, DUMMY_ANALYSIS, db_session, client))

    saved = db_session.query(PlanItem).filter_by(session_id=session.id).all()
    assert len(saved) == 6


def test_build_plan_all_included_by_default(db_session):
    session = make_session(db_session)
    client = MockLLMClient()

    items = asyncio.run(build_plan(session.id, DUMMY_ANALYSIS, db_session, client))

    assert all(i.include for i in items)


def test_build_plan_sort_order_sequential(db_session):
    session = make_session(db_session)
    client = MockLLMClient()

    items = asyncio.run(build_plan(session.id, DUMMY_ANALYSIS, db_session, client))

    orders = [i.sort_order for i in items]
    assert orders == list(range(len(items)))


def test_build_plan_rationale_populated(db_session):
    session = make_session(db_session)
    client = MockLLMClient()

    items = asyncio.run(build_plan(session.id, DUMMY_ANALYSIS, db_session, client))

    # At least some items should have an LLM rationale from the fixture
    rationales = [i.llm_rationale for i in items if i.llm_rationale]
    assert len(rationales) > 0


def test_build_plan_skips_unknown_types(db_session):
    session = make_session(db_session)

    class BrokenClient:
        async def chat(self, **kwargs):
            return '{"items": [{"type": "unknown_garbage", "id": 1}]}'

        async def close(self):
            pass

    items = asyncio.run(build_plan(session.id, DUMMY_ANALYSIS, db_session, BrokenClient()))
    assert items == []
