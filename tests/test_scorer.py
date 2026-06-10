"""Tests for src.tailor.scorer.compute_match_score."""

from datetime import date

from src.models.job import Job
from src.models.skill import Skill
from src.tailor.scorer import (
    MatchScore,
    SkillCoverage,
    _skill_matches,
    compute_match_score,
)

# ---------------------------------------------------------------------------
# SkillCoverage helpers
# ---------------------------------------------------------------------------


def test_skill_coverage_pct_all_matched():
    cov = SkillCoverage(matched=["Python", "Go"], missing=[])
    assert cov.pct == 100


def test_skill_coverage_pct_none_matched():
    cov = SkillCoverage(matched=[], missing=["Python", "Go"])
    assert cov.pct == 0


def test_skill_coverage_pct_partial():
    cov = SkillCoverage(matched=["Python"], missing=["Go", "Rust", "Java"])
    assert cov.pct == 25


def test_skill_coverage_pct_empty_is_100():
    cov = SkillCoverage(matched=[], missing=[])
    assert cov.pct == 100


# ---------------------------------------------------------------------------
# _skill_matches
# ---------------------------------------------------------------------------


def test_skill_matches_exact():
    assert _skill_matches({"python"}, "Python") is True


def test_skill_matches_substring_candidate_in_target():
    # "sql" is in "postgresql"
    assert _skill_matches({"sql"}, "PostgreSQL") is True


def test_skill_matches_substring_target_in_candidate():
    # "postgresql" is in "postgresql experience"
    assert _skill_matches({"postgresql experience"}, "PostgreSQL") is True


def test_skill_matches_no_match():
    assert _skill_matches({"java", "go"}, "Python") is False


def test_skill_matches_empty_candidates():
    assert _skill_matches(set(), "Python") is False


# ---------------------------------------------------------------------------
# compute_match_score — skill matching
# ---------------------------------------------------------------------------


def _add_skills(db_session, names: list[str]) -> None:
    for name in names:
        db_session.add(Skill(name=name))
    db_session.commit()


def _add_job(db_session, title: str, is_technical: bool = True) -> Job:
    j = Job(title=title, company="Acme", start_date=date(2020, 1, 1), is_technical=is_technical)
    db_session.add(j)
    db_session.commit()
    return j


def test_all_required_skills_matched(db_session):
    _add_skills(db_session, ["Python", "Docker"])
    analysis = {
        "required_skills": ["Python", "Docker"],
        "preferred_skills": [],
        "role_level": "",
        "domain": "",
    }
    score = compute_match_score(analysis, db_session)
    assert set(score.required.matched) == {"Python", "Docker"}
    assert score.required.missing == []
    assert score.required.pct == 100


def test_missing_required_skill(db_session):
    _add_skills(db_session, ["Python"])
    analysis = {
        "required_skills": ["Python", "Kubernetes"],
        "preferred_skills": [],
        "role_level": "",
        "domain": "",
    }
    score = compute_match_score(analysis, db_session)
    assert "Python" in score.required.matched
    assert "Kubernetes" in score.required.missing


def test_preferred_skills_matched_and_missing(db_session):
    _add_skills(db_session, ["React"])
    analysis = {
        "required_skills": [],
        "preferred_skills": ["React", "Vue"],
        "role_level": "",
        "domain": "",
    }
    score = compute_match_score(analysis, db_session)
    assert "React" in score.preferred.matched
    assert "Vue" in score.preferred.missing


def test_case_insensitive_matching(db_session):
    _add_skills(db_session, ["python"])
    analysis = {
        "required_skills": ["Python"],
        "preferred_skills": [],
        "role_level": "",
        "domain": "",
    }
    score = compute_match_score(analysis, db_session)
    assert "Python" in score.required.matched


def test_substring_matching_sql_in_postgresql(db_session):
    _add_skills(db_session, ["SQL"])
    analysis = {
        "required_skills": ["PostgreSQL"],
        "preferred_skills": [],
        "role_level": "",
        "domain": "",
    }
    score = compute_match_score(analysis, db_session)
    assert "PostgreSQL" in score.required.matched


def test_no_skills_in_db(db_session):
    analysis = {
        "required_skills": ["Python", "Go"],
        "preferred_skills": ["Rust"],
        "role_level": "",
        "domain": "",
    }
    score = compute_match_score(analysis, db_session)
    assert score.required.pct == 0
    assert set(score.required.missing) == {"Python", "Go"}


# ---------------------------------------------------------------------------
# compute_match_score — role level notes
# ---------------------------------------------------------------------------


def test_no_role_level_produces_no_note(db_session):
    _add_job(db_session, "Senior Engineer")
    analysis = {"required_skills": [], "preferred_skills": [], "role_level": "", "domain": ""}
    score = compute_match_score(analysis, db_session)
    assert score.role_level_note is None


def test_over_leveled_note(db_session):
    # "VP Engineering" → vp rank 7 vs junior rank 1, gap > 1 → note generated
    _add_job(db_session, "VP Engineering")
    analysis = {"required_skills": [], "preferred_skills": [], "role_level": "junior", "domain": ""}
    score = compute_match_score(analysis, db_session)
    assert score.role_level_note is not None
    assert "vp" in score.role_level_note.lower()


def test_under_leveled_note(db_session):
    # candidate is junior (rank 1), JD wants principal (rank 5) → gap > 1
    _add_job(db_session, "Junior Developer")
    analysis = {
        "required_skills": [],
        "preferred_skills": [],
        "role_level": "principal",
        "domain": "",
    }
    score = compute_match_score(analysis, db_session)
    assert score.role_level_note is not None
    assert "principal" in score.role_level_note.lower()


def test_adjacent_levels_produce_no_note(db_session):
    # candidate is senior (rank 3), JD wants lead (rank 4) → gap == 1, no note
    _add_job(db_session, "Senior Software Engineer")
    analysis = {"required_skills": [], "preferred_skills": [], "role_level": "lead", "domain": ""}
    score = compute_match_score(analysis, db_session)
    assert score.role_level_note is None


def test_no_jobs_in_db_produces_no_note(db_session):
    analysis = {"required_skills": [], "preferred_skills": [], "role_level": "senior", "domain": ""}
    score = compute_match_score(analysis, db_session)
    assert score.role_level_note is None


# ---------------------------------------------------------------------------
# compute_match_score — domain match
# ---------------------------------------------------------------------------


def test_technical_domain_matches_with_technical_job(db_session):
    _add_job(db_session, "Backend Engineer", is_technical=True)
    analysis = {
        "required_skills": [],
        "preferred_skills": [],
        "role_level": "",
        "domain": "backend",
    }
    score = compute_match_score(analysis, db_session)
    assert score.domain_match is True


def test_technical_domain_no_match_without_technical_job(db_session):
    _add_job(db_session, "Project Manager", is_technical=False)
    analysis = {
        "required_skills": [],
        "preferred_skills": [],
        "role_level": "",
        "domain": "backend",
    }
    score = compute_match_score(analysis, db_session)
    assert score.domain_match is False


def test_non_technical_domain_always_matches(db_session):
    _add_job(db_session, "Project Manager", is_technical=False)
    analysis = {
        "required_skills": [],
        "preferred_skills": [],
        "role_level": "",
        "domain": "marketing",
    }
    score = compute_match_score(analysis, db_session)
    assert score.domain_match is True


def test_empty_domain_always_matches(db_session):
    analysis = {"required_skills": [], "preferred_skills": [], "role_level": "", "domain": ""}
    score = compute_match_score(analysis, db_session)
    assert score.domain_match is True


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


def test_returns_match_score_instance(db_session):
    analysis = {"required_skills": [], "preferred_skills": [], "role_level": "", "domain": ""}
    score = compute_match_score(analysis, db_session)
    assert isinstance(score, MatchScore)
    assert isinstance(score.required, SkillCoverage)
    assert isinstance(score.preferred, SkillCoverage)
