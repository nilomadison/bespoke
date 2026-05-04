"""
Tests for the .docx renderer.

Verifies: correct sections present, no tables (ATS rule), name/contact in header,
experience bullets, projects, education, and that the file serializes to bytes.
"""
import io

from docx.document import Document as DocxDocument

from src.render.docx_renderer import docx_to_bytes, render_to_docx

SAMPLE_GENERATED = {
    "summary": "Experienced backend engineer with a focus on scale.",
    "experience": [
        {
            "company": "Widgets Inc",
            "title": "Staff Engineer",
            "dates": "Jan 2021 – Present",
            "bullets": [
                "Built the API gateway serving 500M requests per day.",
                "Led migration to microservices, cutting deploy time by 80%.",
            ],
        }
    ],
    "skills": "Python, FastAPI, Docker, Kubernetes",
    "projects": [
        {"name": "Bespoke", "description": "LLM-powered resume tailoring tool."}
    ],
    "education": [
        {"institution": "UC Berkeley", "degree": "B.S. Computer Science", "dates": "2012–2016"}
    ],
}

SAMPLE_PROFILE = {
    "full_name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "555-1234",
    "location": "San Francisco, CA",
    "linkedin_url": None,
}


def full_text(doc: Document) -> str:
    return "\n".join(p.text for p in doc.paragraphs)


def test_render_returns_document():
    doc = render_to_docx(SAMPLE_GENERATED, SAMPLE_PROFILE)
    assert isinstance(doc, DocxDocument)


def test_render_includes_candidate_name():
    doc = render_to_docx(SAMPLE_GENERATED, SAMPLE_PROFILE)
    assert "Jane Doe" in full_text(doc)


def test_render_has_all_section_headings():
    doc = render_to_docx(SAMPLE_GENERATED, SAMPLE_PROFILE)
    text = full_text(doc)
    assert "Summary" in text
    assert "Experience" in text
    assert "Skills" in text
    assert "Projects" in text
    assert "Education" in text


def test_render_includes_experience_data():
    doc = render_to_docx(SAMPLE_GENERATED, SAMPLE_PROFILE)
    text = full_text(doc)
    assert "Widgets Inc" in text
    assert "Staff Engineer" in text
    assert "Built the API gateway serving 500M requests per day." in text


def test_render_includes_project():
    doc = render_to_docx(SAMPLE_GENERATED, SAMPLE_PROFILE)
    text = full_text(doc)
    assert "Bespoke" in text
    assert "LLM-powered resume tailoring tool." in text


def test_render_includes_education():
    doc = render_to_docx(SAMPLE_GENERATED, SAMPLE_PROFILE)
    text = full_text(doc)
    assert "UC Berkeley" in text
    assert "B.S. Computer Science" in text


def test_render_no_tables():
    doc = render_to_docx(SAMPLE_GENERATED, SAMPLE_PROFILE)
    assert len(doc.tables) == 0, "ATS rule: no tables allowed"


def test_render_saves_to_bytes():
    doc = render_to_docx(SAMPLE_GENERATED, SAMPLE_PROFILE)
    data = docx_to_bytes(doc)
    assert len(data) > 0
    # Must be a valid ZIP (docx is a ZIP archive)
    assert data[:2] == b"PK"


def test_render_missing_optional_sections():
    minimal = {
        "summary": "Test summary.",
        "experience": [],
        "skills": "",
        "projects": [],
        "education": [],
    }
    doc = render_to_docx(minimal, {"full_name": "Test User", "email": "t@t.com"})
    assert isinstance(doc, DocxDocument)
    assert "Test User" in full_text(doc)


def test_render_contact_info_present():
    doc = render_to_docx(SAMPLE_GENERATED, SAMPLE_PROFILE)
    text = full_text(doc)
    assert "jane@example.com" in text
    assert "555-1234" in text
