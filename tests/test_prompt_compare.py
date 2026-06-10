"""
Tests for the prompt_compare CLI.

The cmd_* functions take the db session directly, so they are testable against
the in-memory fixture db. ANSI color is off under pytest (stdout is not a tty),
so plain-text assertions are safe.
"""

from src.models.tailoring import PlanItem, PlanItemType, TailoringSession, TailoringStatus
from src.tools.prompt_compare import cmd_cover_letter, cmd_list, cmd_plan


def _make_session(db, **overrides) -> TailoringSession:
    fields = {
        "job_title": "Engineer",
        "company_name": "Acme",
        "job_description": "Build things.",
        "status": TailoringStatus.GENERATED,
    }
    fields.update(overrides)
    s = TailoringSession(**fields)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_cmd_list_shows_sessions(db_session, capsys):
    _make_session(db_session, analysis_prompt_version="aaa111bbb222")
    cmd_list(db_session)
    out = capsys.readouterr().out
    assert "Engineer" in out
    assert "aaa111bbb222" in out


def test_cmd_plan_shows_plan_prompt_version(db_session, capsys):
    s1 = _make_session(db_session, plan_prompt_version="planhash0001")
    s2 = _make_session(db_session, plan_prompt_version="planhash0002")
    for s in (s1, s2):
        db_session.add(
            PlanItem(
                session_id=s.id,
                item_type=PlanItemType.ACHIEVEMENT,
                reference_id=1,
                include=True,
                sort_order=0,
            )
        )
    db_session.commit()

    cmd_plan(db_session, s1.id, s2.id)

    out = capsys.readouterr().out
    assert "planhash0001" in out
    assert "planhash0002" in out


def test_cmd_cover_letter_diffs_output(db_session, capsys):
    s1 = _make_session(
        db_session,
        cover_letter_prompt_version="coverhash001",
        cover_letter_json={
            "salutation": "Dear Hiring Team,",
            "paragraphs": ["I build scalable systems."],
            "closing": "Sincerely, A",
        },
    )
    s2 = _make_session(
        db_session,
        cover_letter_prompt_version="coverhash002",
        cover_letter_json={
            "salutation": "Dear Hiring Team,",
            "paragraphs": ["I ship reliable platforms."],
            "closing": "Sincerely, A",
        },
    )

    cmd_cover_letter(db_session, s1.id, s2.id)

    out = capsys.readouterr().out
    assert "coverhash001" in out
    assert "coverhash002" in out
    assert "I build scalable systems." in out
    assert "I ship reliable platforms." in out


def test_cmd_cover_letter_handles_missing_output(db_session, capsys):
    s1 = _make_session(db_session)
    s2 = _make_session(db_session)

    cmd_cover_letter(db_session, s1.id, s2.id)

    out = capsys.readouterr().out
    assert "Neither session has cover letter output." in out
