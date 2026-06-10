"""PDF export tests."""

from src.models.tailoring import TailoringSession, TailoringStatus
from src.render.pdf_renderer import render_to_pdf

GENERATED_JSON = {
    "summary": "Senior backend engineer with scale experience.",
    "experience": [
        {
            "company": "Acme",
            "title": "Staff Engineer",
            "dates": "2021–Now",
            "bullets": ["Cut p99 latency 40%.", "Mentored 4 juniors."],
        }
    ],
    "skills": "Python, Go, Postgres",
    "projects": [{"name": "Bespoke", "description": "Resume tool."}],
    "education": [{"institution": "MIT", "degree": "B.S.", "dates": "2015–2019"}],
    "certifications": [{"name": "AWS SAA", "issuer": "Amazon", "year": "2022"}],
}

PROFILE = {
    "full_name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "555-0100",
    "location": "Brooklyn, NY",
    "linkedin_url": "linkedin.com/in/jane",
}


def test_render_to_pdf_returns_pdf_bytes():
    pdf = render_to_pdf(GENERATED_JSON, PROFILE)
    assert isinstance(pdf, bytes)
    # PDF magic number
    assert pdf[:4] == b"%PDF"


def test_render_to_pdf_handles_minimal_input():
    pdf = render_to_pdf({"summary": "Brief."}, {"full_name": "Test"})
    assert pdf[:4] == b"%PDF"


def test_render_to_pdf_escapes_html_chars():
    # Ampersand and angle brackets must not blow up the PDF mini-XML parser
    pdf = render_to_pdf(
        {"summary": "Built A & B; threshold <5%."},
        PROFILE,
    )
    assert pdf[:4] == b"%PDF"


def _make_generated(db) -> TailoringSession:
    s = TailoringSession(
        job_title="Staff Engineer",
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
        generated_json=GENERATED_JSON,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_export_pdf_route_returns_application_pdf(client, db_session):
    s = _make_generated(db_session)
    resp = client.get(f"/tailor/{s.id}/export.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_export_pdf_uses_filename_with_company_and_title(client, db_session):
    s = _make_generated(db_session)
    resp = client.get(f"/tailor/{s.id}/export.pdf")
    cd = resp.headers["content-disposition"]
    assert "resume_Acme_Staff_Engineer.pdf" in cd


def test_export_pdf_marks_session_exported(client, db_session):
    s = _make_generated(db_session)
    client.get(f"/tailor/{s.id}/export.pdf")
    db_session.refresh(s)
    assert s.status == TailoringStatus.EXPORTED


def test_export_pdf_400_when_not_generated(client, db_session):
    s = TailoringSession(
        job_title="X",
        company_name="Y",
        job_description="Z",
        status=TailoringStatus.DRAFT,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    resp = client.get(f"/tailor/{s.id}/export.pdf")
    assert resp.status_code == 400


def test_export_pdf_uses_edited_generated_json(client, db_session):
    """Edits made to generated_json on the result page must flow into the PDF.

    Compares PDF output before and after an edit — content streams are
    compressed, so we verify by output divergence rather than substring search.
    """
    s = _make_generated(db_session)
    before = client.get(f"/tailor/{s.id}/export.pdf").content

    client.post(
        f"/tailor/{s.id}/result/field",
        data={
            "path": "summary",
            "value": "Hand-edited summary phrase that is much longer than the original "
            "to force a meaningful change in the rendered output.",
        },
    )
    after = client.get(f"/tailor/{s.id}/export.pdf").content

    # Both are valid PDFs and they differ
    assert before[:4] == b"%PDF" and after[:4] == b"%PDF"
    assert before != after
