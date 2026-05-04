"""Tests for src.tailor.resolver.resolve_items_for_display."""
from datetime import date

import pytest

from src.models.achievement import Achievement
from src.models.education import Certification, Education
from src.models.job import Job
from src.models.project import Project
from src.models.tailoring import PlanItem, PlanItemType, TailoringSession, TailoringStatus
from src.tailor.resolver import resolve_items_for_display


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def session(db_session) -> TailoringSession:
    s = TailoringSession(
        job_title="Staff Engineer",
        company_name="Acme",
        job_description="Build things.",
        status=TailoringStatus.ANALYZED,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


@pytest.fixture
def job(db_session) -> Job:
    j = Job(
        title="Senior Engineer",
        company="Acme Corp",
        start_date=date(2020, 1, 1),
    )
    db_session.add(j)
    db_session.commit()
    db_session.refresh(j)
    return j


@pytest.fixture
def achievement(db_session, job) -> Achievement:
    a = Achievement(
        job_id=job.id,
        text="Reduced latency by 40%",
        metric="40% p99 reduction",
    )
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


@pytest.fixture
def project(db_session) -> Project:
    p = Project(name="Open Source CLI", summary="A dev tool.")
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def education(db_session) -> Education:
    e = Education(institution="MIT", degree="B.S. CS", field="Computer Science")
    db_session.add(e)
    db_session.commit()
    db_session.refresh(e)
    return e


@pytest.fixture
def certification(db_session) -> Certification:
    c = Certification(name="AWS Solutions Architect", issuer="Amazon")
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


def _make_item(db_session, session_id, item_type, reference_id, include=True, sort_order=0):
    item = PlanItem(
        session_id=session_id,
        item_type=item_type,
        reference_id=reference_id,
        include=include,
        llm_rationale="Strong signal.",
        sort_order=sort_order,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


# ---------------------------------------------------------------------------
# Basic resolution
# ---------------------------------------------------------------------------

def test_empty_items_returns_empty(db_session):
    result = resolve_items_for_display([], db_session)
    assert result == []


def test_job_item_resolves_text(db_session, session, job):
    item = _make_item(db_session, session.id, PlanItemType.JOB, job.id)
    result = resolve_items_for_display([item], db_session)
    assert len(result) == 1
    assert "Senior Engineer" in result[0]["text"]
    assert "Acme Corp" in result[0]["text"]


def test_achievement_item_includes_metric(db_session, session, achievement):
    item = _make_item(db_session, session.id, PlanItemType.ACHIEVEMENT, achievement.id)
    result = resolve_items_for_display([item], db_session)
    assert "Reduced latency" in result[0]["text"]
    assert "40% p99 reduction" in result[0]["text"]


def test_achievement_without_metric(db_session, session, job):
    a = Achievement(job_id=job.id, text="Led platform migration")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    item = _make_item(db_session, session.id, PlanItemType.ACHIEVEMENT, a.id)
    result = resolve_items_for_display([item], db_session)
    assert result[0]["text"] == "Led platform migration"


def test_project_item_resolves_name(db_session, session, project):
    item = _make_item(db_session, session.id, PlanItemType.PROJECT, project.id)
    result = resolve_items_for_display([item], db_session)
    assert result[0]["text"] == "Open Source CLI"


def test_education_item_resolves_degree_institution(db_session, session, education):
    item = _make_item(db_session, session.id, PlanItemType.EDUCATION, education.id)
    result = resolve_items_for_display([item], db_session)
    assert "B.S. CS" in result[0]["text"]
    assert "MIT" in result[0]["text"]


def test_certification_item_resolves_name_issuer(db_session, session, certification):
    item = _make_item(db_session, session.id, PlanItemType.CERTIFICATION, certification.id)
    result = resolve_items_for_display([item], db_session)
    assert "AWS Solutions Architect" in result[0]["text"]
    assert "Amazon" in result[0]["text"]


def test_skill_group_item_uses_emphasis_note(db_session, session):
    item = PlanItem(
        session_id=session.id,
        item_type=PlanItemType.SKILL_GROUP,
        reference_id=None,
        include=True,
        emphasis_note="Cloud infrastructure",
        sort_order=0,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    result = resolve_items_for_display([item], db_session)
    assert result[0]["text"] == "Cloud infrastructure"


def test_skill_group_without_note_defaults_to_skills(db_session, session):
    item = PlanItem(
        session_id=session.id,
        item_type=PlanItemType.SKILL_GROUP,
        reference_id=None,
        include=True,
        sort_order=0,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    result = resolve_items_for_display([item], db_session)
    assert result[0]["text"] == "Skills"


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------

def test_result_has_required_keys(db_session, session, job):
    item = _make_item(db_session, session.id, PlanItemType.JOB, job.id)
    result = resolve_items_for_display([item], db_session)
    r = result[0]
    assert set(r.keys()) >= {"id", "type", "reference_id", "include", "text", "rationale", "emphasis_note"}


def test_include_flag_preserved(db_session, session, job):
    item = _make_item(db_session, session.id, PlanItemType.JOB, job.id, include=False)
    result = resolve_items_for_display([item], db_session)
    assert result[0]["include"] is False


def test_rationale_preserved(db_session, session, job):
    item = _make_item(db_session, session.id, PlanItemType.JOB, job.id)
    result = resolve_items_for_display([item], db_session)
    assert result[0]["rationale"] == "Strong signal."


# ---------------------------------------------------------------------------
# Ordering and multi-item
# ---------------------------------------------------------------------------

def test_items_sorted_by_sort_order(db_session, session, job, achievement, project):
    item_b = _make_item(db_session, session.id, PlanItemType.JOB, job.id, sort_order=2)
    item_a = _make_item(db_session, session.id, PlanItemType.PROJECT, project.id, sort_order=0)
    item_c = _make_item(db_session, session.id, PlanItemType.ACHIEVEMENT, achievement.id, sort_order=1)

    result = resolve_items_for_display([item_b, item_a, item_c], db_session)
    assert result[0]["id"] == item_a.id
    assert result[1]["id"] == item_c.id
    assert result[2]["id"] == item_b.id


def test_batch_load_no_n_plus_one(db_session, session, job):
    """Multiple items of the same type should all resolve without error."""
    a1 = Achievement(job_id=job.id, text="Achievement one")
    a2 = Achievement(job_id=job.id, text="Achievement two")
    db_session.add_all([a1, a2])
    db_session.commit()

    item1 = _make_item(db_session, session.id, PlanItemType.ACHIEVEMENT, a1.id, sort_order=0)
    item2 = _make_item(db_session, session.id, PlanItemType.ACHIEVEMENT, a2.id, sort_order=1)
    result = resolve_items_for_display([item1, item2], db_session)
    texts = [r["text"] for r in result]
    assert "Achievement one" in texts
    assert "Achievement two" in texts


# ---------------------------------------------------------------------------
# Missing reference (soft FK — record was deleted)
# ---------------------------------------------------------------------------

def test_missing_reference_id_returns_none_text(db_session, session):
    item = PlanItem(
        session_id=session.id,
        item_type=PlanItemType.JOB,
        reference_id=99999,
        include=True,
        sort_order=0,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    result = resolve_items_for_display([item], db_session)
    assert result[0]["text"] is None
