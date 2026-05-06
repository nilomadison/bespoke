"""Dashboard route tests."""
from datetime import date

from src.models.education import Education
from src.models.job import Job, EmploymentType
from src.models.project import Project
from src.models.skill import Skill
from src.models.tailoring import TailoringSession, TailoringStatus


def test_dashboard_renders_at_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"New application" in resp.content


def test_dashboard_lists_recent_sessions(client, db_session):
    s = TailoringSession(
        job_title="Staff Eng", company_name="Widgets",
        job_description="x", status=TailoringStatus.GENERATED,
    )
    db_session.add(s); db_session.commit()
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Staff Eng" in resp.content
    assert b"Widgets" in resp.content


def test_dashboard_shows_match_score_when_analysis_present(client, db_session):
    db_session.add(Skill(name="Python"))
    db_session.commit()
    s = TailoringSession(
        job_title="Eng", company_name="Co", job_description="x",
        status=TailoringStatus.ANALYZED,
        analysis_json={
            "required_skills": ["Python"], "preferred_skills": ["Go"],
            "role_level": "senior", "domain": "backend", "tone": "formal",
            "impact_signals": [], "red_flags": [], "emphasis_guidance": "",
        },
    )
    db_session.add(s); db_session.commit()
    resp = client.get("/")
    # Required 100% (Python matches), Preferred 0% (Go doesn't)
    assert b"Required" in resp.content
    assert b"100%" in resp.content


def test_dashboard_shows_career_data_counts(client, db_session):
    db_session.add(Job(title="Eng", company="Acme",
                       employment_type=EmploymentType.FULL_TIME,
                       start_date=date(2020, 1, 1), is_technical=True, sort_order=0))
    db_session.add(Skill(name="Python"))
    db_session.add(Skill(name="Docker"))
    db_session.add(Project(name="X", summary="y"))
    db_session.add(Education(institution="MIT", degree="B.S.", field="CS"))
    db_session.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    # Counts appear next to each section
    body = resp.content.decode()
    assert "Jobs" in body and ">1<" in body  # 1 job
    assert "Skills" in body and ">2<" in body  # 2 skills


def test_dashboard_warns_when_profile_incomplete(client, db_session):
    # The conftest seeds Profile(id=1, full_name="Test User", email="test@example.com").
    # Clear those so we hit the warning path.
    from src.models.profile import Profile
    p = db_session.get(Profile, 1)
    p.full_name = ""
    p.email = ""
    db_session.commit()
    resp = client.get("/")
    assert b"missing contact info" in resp.content


def test_dashboard_no_warning_when_profile_complete(client, db_session):
    # conftest already seeds a complete profile
    resp = client.get("/")
    assert b"missing contact info" not in resp.content


def test_dashboard_renders_without_sessions(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"No sessions yet" in resp.content
