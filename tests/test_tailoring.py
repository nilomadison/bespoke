"""
Route tests for the tailoring flow.

Covers: session creation, status polling, plan view, toggle, note update, and delete.

Background tasks are NOT run in these tests — we manually set session state to
simulate what the analysis pipeline would produce, keeping tests fast and deterministic.
"""
import pytest

from src.models.tailoring import PlanItem, PlanItemType, TailoringSession, TailoringStatus

GENERATED_JSON = {
    "summary": "Experienced engineer.",
    "experience": [{"company": "Acme", "title": "Engineer", "dates": "2021–Now", "bullets": ["Built X."]}],
    "skills": "Python, Docker",
    "projects": [{"name": "Bespoke", "description": "Resume tool."}],
    "education": [{"institution": "MIT", "degree": "B.S.", "dates": "2015–2019"}],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_session(db, status=TailoringStatus.ANALYZED) -> TailoringSession:
    s = TailoringSession(
        job_title="Staff Engineer",
        company_name="Widgets Inc",
        job_description="Build scalable systems.",
        status=status,
        analysis_json={
            "required_skills": ["Python"],
            "preferred_skills": ["Go"],
            "role_level": "staff",
            "domain": "backend",
            "tone": "formal",
            "impact_signals": ["scale"],
            "red_flags": [],
            "emphasis_guidance": "Focus on systems design.",
        },
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def make_plan_item(db, session_id, include=True, emphasis_note=None) -> PlanItem:
    item = PlanItem(
        session_id=session_id,
        item_type=PlanItemType.ACHIEVEMENT,
        reference_id=1,
        include=include,
        emphasis_note=emphasis_note,
        llm_rationale="Demonstrates scale.",
        sort_order=0,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

def test_tailor_index_empty(client):
    resp = client.get("/tailor/")
    assert resp.status_code == 200
    assert b"Staff Engineer" not in resp.content


def test_tailor_index_shows_sessions(client, db_session):
    make_session(db_session)
    resp = client.get("/tailor/")
    assert resp.status_code == 200
    assert b"Widgets Inc" in resp.content


# ---------------------------------------------------------------------------
# New / Create
# ---------------------------------------------------------------------------

def test_new_session_form(client):
    resp = client.get("/tailor/new")
    assert resp.status_code == 200
    assert b"job_description" in resp.content


def test_create_session_redirects(client):
    """POST to /tailor/ should create a session and redirect to the plan page."""
    resp = client.post(
        "/tailor/",
        data={
            "job_title": "Backend Engineer",
            "company_name": "StartupCo",
            "job_description": "We need a great engineer.",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/tailor/" in resp.headers["location"]
    assert "/plan" in resp.headers["location"]


def test_create_session_persists(client, db_session):
    client.post(
        "/tailor/",
        data={
            "job_title": "DevOps Lead",
            "company_name": "CloudCo",
            "job_description": "Manage infra.",
        },
        follow_redirects=False,
    )
    sessions = db_session.query(TailoringSession).all()
    assert any(s.company_name == "CloudCo" for s in sessions)


# ---------------------------------------------------------------------------
# Status polling
# ---------------------------------------------------------------------------

def test_status_returns_spinner_when_analyzing(client, db_session):
    s = make_session(db_session, status=TailoringStatus.ANALYZING)
    resp = client.get(f"/tailor/{s.id}/status")
    assert resp.status_code == 200
    assert b"Analyzing" in resp.content or b"animate-spin" in resp.content


def test_status_redirects_when_analyzed(client, db_session):
    s = make_session(db_session, status=TailoringStatus.ANALYZED)
    resp = client.get(f"/tailor/{s.id}/status", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect") == f"/tailor/{s.id}/plan"


def test_status_returns_error_on_draft_with_message(client, db_session):
    s = TailoringSession(
        job_title="X",
        company_name="Y",
        job_description="Z",
        status=TailoringStatus.DRAFT,
        error_message="LLM timeout",
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)

    resp = client.get(f"/tailor/{s.id}/status")
    assert resp.status_code == 200
    assert b"LLM timeout" in resp.content


def test_status_404_for_missing_session(client):
    resp = client.get("/tailor/99999/status")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Plan view
# ---------------------------------------------------------------------------

def test_plan_shows_analysis_summary(client, db_session):
    s = make_session(db_session)
    resp = client.get(f"/tailor/{s.id}/plan")
    assert resp.status_code == 200
    assert b"Python" in resp.content  # required_skills from analysis_json


def test_plan_shows_spinner_when_analyzing(client, db_session):
    s = make_session(db_session, status=TailoringStatus.ANALYZING)
    resp = client.get(f"/tailor/{s.id}/plan")
    assert resp.status_code == 200
    assert b"animate-spin" in resp.content


def test_plan_shows_items(client, db_session):
    s = make_session(db_session)
    make_plan_item(db_session, s.id)
    resp = client.get(f"/tailor/{s.id}/plan")
    assert resp.status_code == 200
    assert b"achievement" in resp.content


# ---------------------------------------------------------------------------
# Toggle
# ---------------------------------------------------------------------------

def test_toggle_flips_include(client, db_session):
    s = make_session(db_session)
    item = make_plan_item(db_session, s.id, include=True)

    resp = client.post(f"/tailor/{s.id}/plan/{item.id}/toggle")
    assert resp.status_code == 200

    db_session.refresh(item)
    assert item.include is False


def test_toggle_twice_restores_include(client, db_session):
    s = make_session(db_session)
    item = make_plan_item(db_session, s.id, include=True)

    client.post(f"/tailor/{s.id}/plan/{item.id}/toggle")
    client.post(f"/tailor/{s.id}/plan/{item.id}/toggle")

    db_session.refresh(item)
    assert item.include is True


def test_toggle_marks_session_plan_edited(client, db_session):
    s = make_session(db_session, status=TailoringStatus.ANALYZED)
    item = make_plan_item(db_session, s.id)

    client.post(f"/tailor/{s.id}/plan/{item.id}/toggle")

    db_session.refresh(s)
    assert s.status == TailoringStatus.PLAN_EDITED


def test_toggle_returns_item_fragment(client, db_session):
    s = make_session(db_session)
    item = make_plan_item(db_session, s.id)

    resp = client.post(f"/tailor/{s.id}/plan/{item.id}/toggle")
    assert resp.status_code == 200
    assert b"plan-item-" in resp.content


def test_toggle_wrong_session_returns_404(client, db_session):
    s1 = make_session(db_session)
    s2 = make_session(db_session)
    item = make_plan_item(db_session, s1.id)

    resp = client.post(f"/tailor/{s2.id}/plan/{item.id}/toggle")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Note update
# ---------------------------------------------------------------------------

def test_note_saves(client, db_session):
    s = make_session(db_session)
    item = make_plan_item(db_session, s.id)

    resp = client.post(
        f"/tailor/{s.id}/plan/{item.id}/note",
        data={"emphasis_note": "Focus on reliability."},
    )
    assert resp.status_code == 200

    db_session.refresh(item)
    assert item.emphasis_note == "Focus on reliability."


def test_note_blank_clears_to_none(client, db_session):
    s = make_session(db_session)
    item = make_plan_item(db_session, s.id, emphasis_note="Old note")

    client.post(
        f"/tailor/{s.id}/plan/{item.id}/note",
        data={"emphasis_note": "   "},
    )

    db_session.refresh(item)
    assert item.emphasis_note is None


def test_note_marks_session_plan_edited(client, db_session):
    s = make_session(db_session, status=TailoringStatus.ANALYZED)
    item = make_plan_item(db_session, s.id)

    client.post(
        f"/tailor/{s.id}/plan/{item.id}/note",
        data={"emphasis_note": "New emphasis."},
    )

    db_session.refresh(s)
    assert s.status == TailoringStatus.PLAN_EDITED


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_removes_session(client, db_session):
    s = make_session(db_session)
    sid = s.id

    resp = client.post(f"/tailor/{sid}/delete", follow_redirects=False)
    assert resp.status_code == 303

    deleted = db_session.get(TailoringSession, sid)
    assert deleted is None


def test_delete_nonexistent_is_safe(client):
    resp = client.post("/tailor/99999/delete", follow_redirects=False)
    assert resp.status_code == 303


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------

def test_generate_redirects_to_result(client, db_session):
    s = make_session(db_session)
    resp = client.post(f"/tailor/{s.id}/generate", follow_redirects=False)
    assert resp.status_code == 303
    assert "/result" in resp.headers["location"]


def test_generate_sets_generating_status(client, db_session):
    s = make_session(db_session)
    client.post(f"/tailor/{s.id}/generate", follow_redirects=False)
    db_session.refresh(s)
    assert s.status == TailoringStatus.GENERATING


def test_generate_404_for_missing_session(client):
    resp = client.post("/tailor/99999/generate", follow_redirects=False)
    assert resp.status_code == 404


def test_status_redirects_to_result_when_generated(client, db_session):
    s = make_session(db_session, status=TailoringStatus.GENERATED)
    resp = client.get(f"/tailor/{s.id}/status", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect") == f"/tailor/{s.id}/result"


# ---------------------------------------------------------------------------
# Result page
# ---------------------------------------------------------------------------

def test_result_shows_spinner_when_generating(client, db_session):
    s = make_session(db_session, status=TailoringStatus.GENERATING)
    resp = client.get(f"/tailor/{s.id}/result")
    assert resp.status_code == 200
    assert b"animate-spin" in resp.content


def test_result_shows_generated_resume(client, db_session):
    s = TailoringSession(
        job_title="Staff Engineer",
        company_name="Acme",
        job_description="Build stuff.",
        status=TailoringStatus.GENERATED,
        analysis_json={
            "required_skills": ["Python"], "preferred_skills": [], "role_level": "senior",
            "domain": "backend", "tone": "formal", "impact_signals": [], "red_flags": [],
            "emphasis_guidance": "",
        },
        generated_json=GENERATED_JSON,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)

    resp = client.get(f"/tailor/{s.id}/result")
    assert resp.status_code == 200
    assert b"Experienced engineer." in resp.content
    assert b"Export .docx" in resp.content


def test_result_404_for_missing_session(client):
    resp = client.get("/tailor/99999/result")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def test_export_returns_docx(client, db_session):
    s = TailoringSession(
        job_title="Staff Engineer",
        company_name="Acme",
        job_description="Build stuff.",
        status=TailoringStatus.GENERATED,
        analysis_json={
            "required_skills": ["Python"], "preferred_skills": [], "role_level": "senior",
            "domain": "backend", "tone": "formal", "impact_signals": [], "red_flags": [],
            "emphasis_guidance": "",
        },
        generated_json=GENERATED_JSON,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)

    resp = client.post(f"/tailor/{s.id}/export")
    assert resp.status_code == 200
    assert "wordprocessingml" in resp.headers["content-type"]
    assert resp.content[:2] == b"PK"


def test_export_marks_session_exported(client, db_session):
    s = TailoringSession(
        job_title="Staff Engineer",
        company_name="Acme",
        job_description="Build stuff.",
        status=TailoringStatus.GENERATED,
        analysis_json={
            "required_skills": ["Python"], "preferred_skills": [], "role_level": "senior",
            "domain": "backend", "tone": "formal", "impact_signals": [], "red_flags": [],
            "emphasis_guidance": "",
        },
        generated_json=GENERATED_JSON,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)

    client.post(f"/tailor/{s.id}/export")
    db_session.refresh(s)
    assert s.status == TailoringStatus.EXPORTED


def test_export_400_when_not_generated(client, db_session):
    s = make_session(db_session)
    resp = client.post(f"/tailor/{s.id}/export")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Cover letter — start (POST)
# ---------------------------------------------------------------------------

def make_generated_session(db_session) -> TailoringSession:
    s = TailoringSession(
        job_title="Staff Engineer",
        company_name="Acme",
        job_description="Build things.",
        status=TailoringStatus.GENERATED,
        analysis_json={
            "required_skills": ["Python"],
            "preferred_skills": [],
            "role_level": "senior",
            "domain": "backend",
            "tone": "formal",
            "impact_signals": [],
            "red_flags": [],
            "emphasis_guidance": "",
        },
        generated_json=GENERATED_JSON,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


def test_start_cover_letter_redirects(client, db_session):
    s = make_generated_session(db_session)
    resp = client.post(f"/tailor/{s.id}/cover-letter", follow_redirects=False)
    assert resp.status_code == 303
    assert f"/tailor/{s.id}/cover-letter" in resp.headers["location"]


def test_start_cover_letter_sets_generating_flag(client, db_session):
    s = make_generated_session(db_session)
    client.post(f"/tailor/{s.id}/cover-letter", follow_redirects=False)
    db_session.refresh(s)
    assert s.cover_letter_generating is True


def test_start_cover_letter_clears_existing_json(client, db_session):
    s = make_generated_session(db_session)
    s.cover_letter_json = {"salutation": "old", "paragraphs": [], "closing": "old"}
    db_session.commit()

    client.post(f"/tailor/{s.id}/cover-letter", follow_redirects=False)
    db_session.refresh(s)
    assert s.cover_letter_json is None


def test_start_cover_letter_400_without_generated_json(client, db_session):
    s = make_session(db_session)  # no generated_json
    resp = client.post(f"/tailor/{s.id}/cover-letter", follow_redirects=False)
    assert resp.status_code == 400


def test_start_cover_letter_404_for_missing(client):
    resp = client.post("/tailor/99999/cover-letter", follow_redirects=False)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Cover letter — view (GET)
# ---------------------------------------------------------------------------

def test_view_cover_letter_shows_generate_button_when_no_json(client, db_session):
    s = make_generated_session(db_session)
    resp = client.get(f"/tailor/{s.id}/cover-letter")
    assert resp.status_code == 200
    assert b"Generate cover letter" in resp.content


def test_view_cover_letter_shows_spinner_when_generating(client, db_session):
    s = make_generated_session(db_session)
    s.cover_letter_generating = True
    db_session.commit()

    resp = client.get(f"/tailor/{s.id}/cover-letter")
    assert resp.status_code == 200
    assert b"animate-spin" in resp.content


def test_view_cover_letter_renders_letter_when_json_present(client, db_session):
    s = make_generated_session(db_session)
    s.cover_letter_json = {
        "salutation": "Dear Hiring Team,",
        "paragraphs": ["I am excited to apply."],
        "closing": "Sincerely, Test User",
    }
    db_session.commit()

    resp = client.get(f"/tailor/{s.id}/cover-letter")
    assert resp.status_code == 200
    assert b"Dear Hiring Team," in resp.content
    assert b"I am excited to apply." in resp.content
    assert b"Sincerely, Test User" in resp.content


def test_view_cover_letter_404_for_missing(client):
    resp = client.get("/tailor/99999/cover-letter")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Cover letter — status polling (GET)
# ---------------------------------------------------------------------------

def test_cover_letter_status_spinner_when_generating(client, db_session):
    s = make_generated_session(db_session)
    s.cover_letter_generating = True
    db_session.commit()

    resp = client.get(f"/tailor/{s.id}/cover-letter/status")
    assert resp.status_code == 200
    assert b"animate-spin" in resp.content


def test_cover_letter_status_redirects_when_done(client, db_session):
    s = make_generated_session(db_session)
    s.cover_letter_json = {"salutation": "Hi", "paragraphs": [], "closing": "Bye"}
    db_session.commit()

    resp = client.get(f"/tailor/{s.id}/cover-letter/status", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect") == f"/tailor/{s.id}/cover-letter"


def test_cover_letter_status_404_for_missing(client):
    resp = client.get("/tailor/99999/cover-letter/status")
    assert resp.status_code == 404
