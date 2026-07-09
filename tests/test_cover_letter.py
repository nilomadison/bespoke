"""
Unit tests for the cover letter generator.

Covers: LLM call + DB persistence, prompt-hash recording (the reproducibility
contract every LLM stage must honor), the generating-flag lifecycle, and the
missing-session error path.
"""

import asyncio
from datetime import date

import pytest

from src.llm.mock_client import MockLLMClient
from src.models.achievement import Achievement
from src.models.job import Job
from src.models.tailoring import PlanItem, PlanItemType, TailoringSession, TailoringStatus
from src.tailor.cover_letter import generate_cover_letter


def make_generated_session(db) -> TailoringSession:
    job = Job(
        title="Staff Engineer",
        company="Widgets Inc",
        start_date=date(2021, 1, 1),
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
    db.commit()
    db.refresh(ach)

    session = TailoringSession(
        job_title="Senior Engineer",
        company_name="Acme Corp",
        job_description="Build scalable systems.",
        status=TailoringStatus.GENERATED,
        analysis_json={"required_skills": ["Python"], "tone": "formal"},
        generated_json={"summary": "Engineer.", "experience": [], "skills": ""},
        cover_letter_generating=True,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    db.add_all(
        [
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
        ]
    )
    db.commit()
    db.refresh(session)
    return session


def test_generate_cover_letter_returns_letter(db_session):
    session = make_generated_session(db_session)

    result = asyncio.run(generate_cover_letter(session.id, db_session, MockLLMClient()))

    assert "paragraphs" in result
    assert len(result["paragraphs"]) > 0


def test_generate_cover_letter_stores_on_session(db_session):
    session = make_generated_session(db_session)

    asyncio.run(generate_cover_letter(session.id, db_session, MockLLMClient()))

    db_session.refresh(session)
    assert session.cover_letter_json
    assert session.cover_letter_json.get("paragraphs")
    assert session.cover_letter_generating is False


def test_generate_cover_letter_records_prompt_hash(db_session):
    session = make_generated_session(db_session)

    asyncio.run(generate_cover_letter(session.id, db_session, MockLLMClient()))

    db_session.refresh(session)
    assert session.cover_letter_prompt_version is not None
    assert len(session.cover_letter_prompt_version) == 12


def test_generate_cover_letter_missing_session_raises(db_session):
    with pytest.raises(ValueError, match="not found"):
        asyncio.run(generate_cover_letter(99999, db_session, MockLLMClient()))


def test_generate_cover_letter_bad_json_raises(db_session):
    class BadJSONClient:
        async def chat(self, **kwargs):
            return "this is not json"

        async def close(self):
            pass

    session = make_generated_session(db_session)

    with pytest.raises(ValueError):
        asyncio.run(generate_cover_letter(session.id, db_session, BadJSONClient()))
