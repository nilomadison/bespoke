"""Tests for model constraints, cascade deletes, and DB initialization."""

from datetime import date

from src.models.achievement import Achievement
from src.models.education import Certification, Education
from src.models.job import EmploymentType, Job
from src.models.profile import Profile
from src.models.project import Project
from src.models.skill import Skill


def test_profile_seeded(db_session):
    profile = db_session.get(Profile, 1)
    assert profile is not None
    assert profile.full_name == "Test User"


def test_profile_is_singleton(db_engine, db_session):
    """init_db must not create a second profile row if one exists."""
    from src.db.init_db import init_db

    # init_db should be idempotent — run it against the test engine, which
    # the db_session fixture has already seeded with Profile(id=1)
    init_db(bind=db_engine)
    count = db_session.query(Profile).count()
    assert count == 1


def test_job_cascade_delete_achievements(db_session):
    job = Job(
        title="Eng",
        company="Co",
        start_date=date(2020, 1, 1),
        employment_type=EmploymentType.FULL_TIME,
    )
    db_session.add(job)
    db_session.commit()
    ach = Achievement(job_id=job.id, text="Did X", impact_tags=[], sort_order=0)
    db_session.add(ach)
    db_session.commit()
    ach_id = ach.id

    db_session.delete(job)
    db_session.commit()
    assert db_session.get(Achievement, ach_id) is None


def test_skill_unique_name(db_session):
    import pytest
    from sqlalchemy.exc import IntegrityError

    db_session.add(Skill(name="Python", category="Languages"))
    db_session.commit()
    db_session.add(Skill(name="Python", category="Other"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_education_model(db_session):
    edu = Education(institution="MIT", degree="M.S.", field="CS", is_in_progress=False)
    db_session.add(edu)
    db_session.commit()
    result = db_session.get(Education, edu.id)
    assert result.institution == "MIT"
    assert result.gpa is None


def test_certification_model(db_session):
    cert = Certification(name="AWS SAA", issuer="Amazon")
    db_session.add(cert)
    db_session.commit()
    result = db_session.get(Certification, cert.id)
    assert result.name == "AWS SAA"


def test_project_optional_job_link(db_session):
    project = Project(name="Bespoke", summary="Resume tool", is_active=True)
    db_session.add(project)
    db_session.commit()
    result = db_session.get(Project, project.id)
    assert result.job_id is None


def test_achievement_impact_tags_json(db_session):
    job = Job(
        title="Dev",
        company="X",
        start_date=date(2021, 1, 1),
        employment_type=EmploymentType.FULL_TIME,
    )
    db_session.add(job)
    db_session.commit()
    ach = Achievement(
        job_id=job.id,
        text="Did something",
        impact_tags=["scale", "cost_reduction", "leadership"],
        sort_order=0,
    )
    db_session.add(ach)
    db_session.commit()
    db_session.expire_all()
    result = db_session.get(Achievement, ach.id)
    assert isinstance(result.impact_tags, list)
    assert "scale" in result.impact_tags
    assert len(result.impact_tags) == 3
