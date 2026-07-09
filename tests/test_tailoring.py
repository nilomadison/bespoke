"""
Route tests for the tailoring flow.

Covers: session creation, status polling, plan view, toggle, note update, and delete.

Background tasks are NOT run in these tests — we manually set session state to
simulate what the analysis pipeline would produce, keeping tests fast and deterministic.
"""

from sqlalchemy import select

from src.models.tailoring import PlanItem, PlanItemType, TailoringSession, TailoringStatus

GENERATED_JSON = {
    "summary": "Experienced engineer.",
    "experience": [
        {"company": "Acme", "title": "Engineer", "dates": "2021–Now", "bullets": ["Built X."]}
    ],
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


def test_generate_idempotent_while_generating(client, db_session, monkeypatch):
    calls = []
    monkeypatch.setattr("src.web.routes.tailor._run_generation_sync", lambda sid: calls.append(sid))
    s = make_session(db_session)

    client.post(f"/tailor/{s.id}/generate", follow_redirects=False)
    resp = client.post(f"/tailor/{s.id}/generate", follow_redirects=False)

    assert resp.status_code == 303
    assert "/result" in resp.headers["location"]
    assert len(calls) == 1


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
    s.cover_letter_prompt_version = "abc123def456"
    s.error_message = "old failure"
    db_session.commit()

    client.post(f"/tailor/{s.id}/cover-letter", follow_redirects=False)
    db_session.refresh(s)
    assert s.cover_letter_json is None
    assert s.cover_letter_prompt_version is None
    assert s.error_message is None


def test_start_cover_letter_idempotent_while_generating(client, db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "src.web.routes.tailor._run_cover_letter_sync", lambda sid: calls.append(sid)
    )
    s = make_generated_session(db_session)

    client.post(f"/tailor/{s.id}/cover-letter", follow_redirects=False)
    resp = client.post(f"/tailor/{s.id}/cover-letter", follow_redirects=False)

    assert resp.status_code == 303
    assert len(calls) == 1


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


def test_cover_letter_status_shows_error_on_failure(client, db_session):
    s = make_generated_session(db_session)
    s.cover_letter_generating = False
    s.error_message = "LLM exploded"
    db_session.commit()

    resp = client.get(f"/tailor/{s.id}/cover-letter/status", follow_redirects=False)
    assert resp.status_code == 200
    assert "HX-Redirect" not in resp.headers
    assert b"Cover letter generation failed" in resp.content
    assert b"LLM exploded" in resp.content
    # The error partial keeps the swap target id so HTMX replaces the spinner in place
    assert b'id="cover-letter-status"' in resp.content


def test_cover_letter_status_redirects_when_idle_no_error(client, db_session):
    # Safety net: not generating, no result, no error — stop polling, don't spin forever
    s = make_generated_session(db_session)
    resp = client.get(f"/tailor/{s.id}/cover-letter/status", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect") == f"/tailor/{s.id}/cover-letter"


def test_view_cover_letter_shows_error_with_retry(client, db_session):
    s = make_generated_session(db_session)
    s.cover_letter_generating = False
    s.error_message = "LLM exploded"
    db_session.commit()

    resp = client.get(f"/tailor/{s.id}/cover-letter")
    assert resp.status_code == 200
    assert b"Cover letter generation failed" in resp.content
    assert b"LLM exploded" in resp.content
    assert f'action="/tailor/{s.id}/cover-letter"'.encode() in resp.content


# ---------------------------------------------------------------------------
# Retry analysis / generation
# ---------------------------------------------------------------------------


def test_retry_analysis_clears_plan_items_and_resets_status(client, db_session):
    s = TailoringSession(
        job_title="Staff Engineer",
        company_name="Widgets Inc",
        job_description="Build scalable systems.",
        status=TailoringStatus.DRAFT,
        analysis_json={
            "required_skills": ["Python"],
            "preferred_skills": [],
            "role_level": "staff",
            "domain": "backend",
            "tone": "formal",
            "impact_signals": [],
            "red_flags": [],
            "emphasis_guidance": "",
        },
        analysis_prompt_version="abc123",
        plan_prompt_version="def456",
        error_message="LLM timeout",
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    make_plan_item(db_session, s.id)
    make_plan_item(db_session, s.id)

    resp = client.post(f"/tailor/{s.id}/retry-analysis", follow_redirects=False)
    assert resp.status_code == 303
    assert f"/tailor/{s.id}/plan" in resp.headers["location"]

    db_session.refresh(s)
    assert s.status == TailoringStatus.ANALYZING
    assert s.analysis_json is None
    assert s.analysis_prompt_version is None
    assert s.plan_prompt_version is None
    assert s.error_message is None
    assert len(s.plan_items) == 0
    # Crucially, the JD survives so the user doesn't lose their paste
    assert s.job_description == "Build scalable systems."


def test_retry_analysis_404_for_missing(client):
    resp = client.post("/tailor/99999/retry-analysis", follow_redirects=False)
    assert resp.status_code == 404


def test_retry_generation_clears_generated_json_and_resets_status(client, db_session):
    s = make_session(db_session, status=TailoringStatus.PLAN_EDITED)
    s.generated_json = GENERATED_JSON
    s.generation_prompt_version = "def456"
    s.error_message = "Schema validation failed"
    db_session.commit()
    make_plan_item(db_session, s.id)

    resp = client.post(f"/tailor/{s.id}/retry-generation", follow_redirects=False)
    assert resp.status_code == 303
    assert f"/tailor/{s.id}/result" in resp.headers["location"]

    db_session.refresh(s)
    assert s.status == TailoringStatus.GENERATING
    assert s.generated_json is None
    assert s.generation_prompt_version is None
    assert s.error_message is None
    # Plan items survive a generation retry
    assert len(s.plan_items) == 1


def test_retry_generation_404_for_missing(client):
    resp = client.post("/tailor/99999/retry-generation", follow_redirects=False)
    assert resp.status_code == 404


def test_plan_page_shows_error_with_retry_button(client, db_session):
    s = TailoringSession(
        job_title="X",
        company_name="Y",
        job_description="Z",
        status=TailoringStatus.DRAFT,
        error_message="Connection refused",
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)

    resp = client.get(f"/tailor/{s.id}/plan")
    assert resp.status_code == 200
    assert b"Connection refused" in resp.content
    assert b"Retry analysis" in resp.content
    assert f"/tailor/{s.id}/retry-analysis".encode() in resp.content


def test_result_page_shows_error_with_retry_button(client, db_session):
    s = make_session(db_session, status=TailoringStatus.PLAN_EDITED)
    s.error_message = "Generator returned malformed JSON"
    db_session.commit()

    resp = client.get(f"/tailor/{s.id}/result")
    assert resp.status_code == 200
    assert b"Generator returned malformed JSON" in resp.content
    assert b"Retry generation" in resp.content
    assert f"/tailor/{s.id}/retry-generation".encode() in resp.content


# ---------------------------------------------------------------------------
# Reorder plan items
# ---------------------------------------------------------------------------


def test_reorder_updates_sort_order(client, db_session):
    s = make_session(db_session)
    a = make_plan_item(db_session, s.id)
    b = make_plan_item(db_session, s.id)
    c = make_plan_item(db_session, s.id)

    # Reverse the order
    resp = client.post(
        f"/tailor/{s.id}/plan/reorder",
        data={"item_ids": [c.id, b.id, a.id]},
    )
    assert resp.status_code == 204

    db_session.refresh(a)
    db_session.refresh(b)
    db_session.refresh(c)
    assert c.sort_order == 0
    assert b.sort_order == 10
    assert a.sort_order == 20


def test_reorder_marks_session_plan_edited(client, db_session):
    s = make_session(db_session, status=TailoringStatus.ANALYZED)
    a = make_plan_item(db_session, s.id)
    b = make_plan_item(db_session, s.id)

    client.post(
        f"/tailor/{s.id}/plan/reorder",
        data={"item_ids": [b.id, a.id]},
    )
    db_session.refresh(s)
    assert s.status == TailoringStatus.PLAN_EDITED


def test_reorder_rejects_foreign_item_ids(client, db_session):
    s1 = make_session(db_session)
    s2 = make_session(db_session)
    a = make_plan_item(db_session, s1.id)
    b = make_plan_item(db_session, s2.id)

    # Try to reorder s1's plan including an item from s2
    resp = client.post(
        f"/tailor/{s1.id}/plan/reorder",
        data={"item_ids": [a.id, b.id]},
    )
    assert resp.status_code == 400


def test_reorder_rejects_partial_item_ids(client, db_session):
    s = make_session(db_session)
    a = make_plan_item(db_session, s.id)
    make_plan_item(db_session, s.id)

    resp = client.post(
        f"/tailor/{s.id}/plan/reorder",
        data={"item_ids": [a.id]},  # missing the other item
    )
    assert resp.status_code == 400


def test_reorder_404_for_missing_session(client):
    resp = client.post(
        "/tailor/99999/plan/reorder",
        data={"item_ids": [1]},
    )
    assert resp.status_code == 404


def test_plan_item_renders_drag_handle(client, db_session):
    s = make_session(db_session)
    make_plan_item(db_session, s.id)
    resp = client.get(f"/tailor/{s.id}/plan")
    assert resp.status_code == 200
    assert b"plan-item-drag-handle" in resp.content
    assert b"data-item-id" in resp.content


# ---------------------------------------------------------------------------
# Add custom plan item — picker (GET) and create (POST)
# ---------------------------------------------------------------------------


def _make_achievement(db, job_id: int, text: str = "Built thing.", metric: str | None = None):
    from src.models.achievement import Achievement

    a = Achievement(job_id=job_id, text=text, metric=metric, sort_order=0)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _make_job(db, title: str = "Engineer", company: str = "Acme"):
    from datetime import date

    from src.models.job import EmploymentType, Job

    j = Job(
        title=title,
        company=company,
        employment_type=EmploymentType.FULL_TIME,
        start_date=date(2020, 1, 1),
        is_technical=True,
        sort_order=0,
    )
    db.add(j)
    db.commit()
    db.refresh(j)
    return j


def test_picker_lists_unused_achievements(client, db_session):
    s = make_session(db_session)
    j = _make_job(db_session)
    a1 = _make_achievement(db_session, j.id, text="Reduced latency 50%.")
    _make_achievement(db_session, j.id, text="Mentored 4 juniors.")

    # Put a1 on the plan; a2 should be available in the picker
    item = PlanItem(
        session_id=s.id,
        item_type=PlanItemType.ACHIEVEMENT,
        reference_id=a1.id,
        include=True,
        sort_order=0,
    )
    db_session.add(item)
    db_session.commit()

    resp = client.get(f"/tailor/{s.id}/plan/add")
    assert resp.status_code == 200
    assert b"Mentored 4 juniors." in resp.content
    assert b"Reduced latency 50%." not in resp.content


def test_picker_404_for_missing_session(client):
    resp = client.get("/tailor/99999/plan/add")
    assert resp.status_code == 404


def test_add_achievement_creates_planitem(client, db_session):
    s = make_session(db_session)
    j = _make_job(db_session)
    a = _make_achievement(db_session, j.id, text="Shipped feature.")

    resp = client.post(
        f"/tailor/{s.id}/plan/add",
        data={"item_type": "achievement", "reference_id": a.id},
    )
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect") == f"/tailor/{s.id}/plan"

    items = [
        i for i in db_session.scalars(select(PlanItem).where(PlanItem.session_id == s.id)).all()
    ]
    assert len(items) == 1
    assert items[0].item_type == PlanItemType.ACHIEVEMENT
    assert items[0].reference_id == a.id
    assert items[0].include is True
    assert items[0].llm_rationale == "Added by user"


def test_add_skill_group_uses_emphasis_note(client, db_session):
    s = make_session(db_session)
    resp = client.post(
        f"/tailor/{s.id}/plan/add",
        data={"item_type": "skill_group", "emphasis_note": "Kubernetes, Terraform"},
    )
    assert resp.status_code == 200

    items = list(db_session.scalars(select(PlanItem).where(PlanItem.session_id == s.id)).all())
    assert len(items) == 1
    assert items[0].item_type == PlanItemType.SKILL_GROUP
    assert items[0].reference_id is None
    assert items[0].emphasis_note == "Kubernetes, Terraform"


def test_add_skill_group_rejects_empty_note(client, db_session):
    s = make_session(db_session)
    resp = client.post(
        f"/tailor/{s.id}/plan/add",
        data={"item_type": "skill_group", "emphasis_note": "   "},
    )
    assert resp.status_code == 400


def test_add_rejects_invalid_item_type(client, db_session):
    s = make_session(db_session)
    resp = client.post(
        f"/tailor/{s.id}/plan/add",
        data={"item_type": "bogus", "reference_id": 1},
    )
    assert resp.status_code == 400


def test_add_rejects_unknown_reference_id(client, db_session):
    s = make_session(db_session)
    resp = client.post(
        f"/tailor/{s.id}/plan/add",
        data={"item_type": "achievement", "reference_id": 99999},
    )
    assert resp.status_code == 400


def test_add_marks_session_plan_edited(client, db_session):
    s = make_session(db_session, status=TailoringStatus.ANALYZED)
    j = _make_job(db_session)
    a = _make_achievement(db_session, j.id)

    client.post(
        f"/tailor/{s.id}/plan/add",
        data={"item_type": "achievement", "reference_id": a.id},
    )
    db_session.refresh(s)
    assert s.status == TailoringStatus.PLAN_EDITED


# ---------------------------------------------------------------------------
# Inline-editable result page
# ---------------------------------------------------------------------------


def _make_generated(db) -> TailoringSession:
    s = TailoringSession(
        job_title="Eng",
        company_name="Acme",
        job_description="x",
        status=TailoringStatus.GENERATED,
        analysis_json={
            "required_skills": [],
            "preferred_skills": [],
            "role_level": "senior",
            "domain": "b",
            "tone": "f",
            "impact_signals": [],
            "red_flags": [],
            "emphasis_guidance": "",
        },
        generated_json={
            "summary": "Original summary.",
            "skills": "Python, Go",
            "experience": [
                {
                    "title": "Engineer",
                    "company": "Acme",
                    "dates": "2021–Now",
                    "bullets": ["Built X.", "Shipped Y."],
                },
                {
                    "title": "Junior Eng",
                    "company": "Beta",
                    "dates": "2019–2021",
                    "bullets": ["Did Z."],
                },
            ],
            "projects": [{"name": "Bespoke", "description": "Tool."}],
            "education": [{"degree": "B.S.", "institution": "MIT", "dates": "2015–2019"}],
            "certifications": [{"name": "AWS SAA", "issuer": "Amazon", "year": "2022"}],
        },
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_edit_summary_persists(client, db_session):
    s = _make_generated(db_session)
    resp = client.post(
        f"/tailor/{s.id}/result/field",
        data={"path": "summary", "value": "New polished summary."},
    )
    assert resp.status_code == 200
    db_session.refresh(s)
    assert s.generated_json["summary"] == "New polished summary."
    # Other fields unchanged
    assert s.generated_json["skills"] == "Python, Go"


def test_edit_bullet_persists(client, db_session):
    s = _make_generated(db_session)
    resp = client.post(
        f"/tailor/{s.id}/result/field",
        data={"path": "experience.0.bullets.1", "value": "Shipped Y on time."},
    )
    assert resp.status_code == 200
    db_session.refresh(s)
    assert s.generated_json["experience"][0]["bullets"][1] == "Shipped Y on time."
    # Sibling bullets unchanged
    assert s.generated_json["experience"][0]["bullets"][0] == "Built X."


def test_edit_experience_title(client, db_session):
    s = _make_generated(db_session)
    resp = client.post(
        f"/tailor/{s.id}/result/field",
        data={"path": "experience.1.title", "value": "Software Engineer"},
    )
    assert resp.status_code == 200
    db_session.refresh(s)
    assert s.generated_json["experience"][1]["title"] == "Software Engineer"


def test_edit_invalid_path_rejected(client, db_session):
    s = _make_generated(db_session)
    resp = client.post(
        f"/tailor/{s.id}/result/field",
        data={"path": "experience.0.malicious_field", "value": "x"},
    )
    assert resp.status_code == 400


def test_edit_arbitrary_top_level_path_rejected(client, db_session):
    s = _make_generated(db_session)
    resp = client.post(
        f"/tailor/{s.id}/result/field",
        data={"path": "__class__", "value": "x"},
    )
    assert resp.status_code == 400


def test_edit_out_of_range_index_rejected(client, db_session):
    s = _make_generated(db_session)
    resp = client.post(
        f"/tailor/{s.id}/result/field",
        data={"path": "experience.99.title", "value": "x"},
    )
    assert resp.status_code == 400


def test_add_bullet_appends_empty_string(client, db_session):
    s = _make_generated(db_session)
    resp = client.post(
        f"/tailor/{s.id}/result/bullet/add",
        data={"experience_index": 0},
    )
    assert resp.status_code == 200
    db_session.refresh(s)
    assert len(s.generated_json["experience"][0]["bullets"]) == 3
    assert s.generated_json["experience"][0]["bullets"][2] == ""


def test_delete_bullet_removes_index(client, db_session):
    s = _make_generated(db_session)
    resp = client.post(
        f"/tailor/{s.id}/result/bullet/delete",
        data={"experience_index": 0, "bullet_index": 0},
    )
    assert resp.status_code == 200
    db_session.refresh(s)
    assert s.generated_json["experience"][0]["bullets"] == ["Shipped Y."]


def test_export_uses_edited_text(client, db_session):
    s = _make_generated(db_session)
    client.post(
        f"/tailor/{s.id}/result/field",
        data={"path": "summary", "value": "Hand-polished summary."},
    )
    resp = client.post(f"/tailor/{s.id}/export")
    assert resp.status_code == 200
    # The .docx is binary; just confirm export completes and the JSON now reflects the edit
    db_session.refresh(s)
    assert s.generated_json["summary"] == "Hand-polished summary."


def test_edit_404_when_no_generated_json(client, db_session):
    s = make_session(db_session)
    resp = client.post(
        f"/tailor/{s.id}/result/field",
        data={"path": "summary", "value": "x"},
    )
    assert resp.status_code == 404


def test_add_uses_increasing_sort_order(client, db_session):
    s = make_session(db_session)
    j = _make_job(db_session)
    a1 = _make_achievement(db_session, j.id, text="One.")
    a2 = _make_achievement(db_session, j.id, text="Two.")

    # Existing item with sort_order=50 — added items should land after
    existing = PlanItem(
        session_id=s.id,
        item_type=PlanItemType.ACHIEVEMENT,
        reference_id=a1.id,
        sort_order=50,
        include=True,
    )
    db_session.add(existing)
    db_session.commit()

    client.post(
        f"/tailor/{s.id}/plan/add",
        data={"item_type": "achievement", "reference_id": a2.id},
    )
    new_items = [
        i
        for i in db_session.scalars(
            select(PlanItem).where(PlanItem.session_id == s.id, PlanItem.reference_id == a2.id)
        ).all()
    ]
    assert new_items[0].sort_order == 60
