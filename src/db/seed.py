"""
Dev seed command: python -m src.db.seed

Reads data/seed.yaml and upserts career data into the local SQLite database.
Safe to re-run — existing rows are updated, not duplicated.

Seed file format: see data/seed.yaml.example
"""

import sys
from datetime import date
from pathlib import Path

import yaml

from src.db.engine import SessionLocal
from src.db.init_db import init_db
from src.models.achievement import Achievement
from src.models.education import Certification, Education
from src.models.job import EmploymentType, Job
from src.models.profile import Profile
from src.models.project import Project
from src.models.skill import JobSkill, Skill


def _date(val: str | None) -> date | None:
    if not val:
        return None
    return date.fromisoformat(str(val))


def seed(seed_file: Path) -> None:
    print(f"Seeding from {seed_file}...")
    data = yaml.safe_load(seed_file.read_text())

    init_db()
    db = SessionLocal()

    try:
        # Profile
        if p := data.get("profile"):
            profile = db.get(Profile, 1)
            profile.full_name = p.get("full_name", profile.full_name)
            profile.email = p.get("email", profile.email)
            profile.phone = p.get("phone")
            profile.location = p.get("location")
            profile.linkedin_url = p.get("linkedin_url")
            profile.github_url = p.get("github_url")
            profile.portfolio_url = p.get("portfolio_url") or None
            profile.baseline_summary = p.get("baseline_summary")
            db.commit()
            print("  Profile updated.")

        # Skills (upsert by name)
        skill_map: dict[str, Skill] = {}
        for s in data.get("skills", []):
            existing = db.query(Skill).filter(Skill.name == s["name"]).first()
            if existing:
                existing.category = s.get("category")
                skill_map[s["name"]] = existing
            else:
                skill = Skill(name=s["name"], category=s.get("category"))
                db.add(skill)
                db.flush()
                skill_map[s["name"]] = skill
        db.commit()
        print(f"  {len(data.get('skills', []))} skills upserted.")

        # Jobs + achievements (clear and re-insert by title+company)
        job_map: dict[tuple[str, str], Job] = {}
        js_total = 0
        for j in data.get("jobs", []):
            existing_job = (
                db.query(Job).filter(Job.title == j["title"], Job.company == j["company"]).first()
            )
            if existing_job:
                job = existing_job
                job.location = j.get("location")
                job.start_date = _date(j["start_date"])
                job.end_date = _date(j.get("end_date"))
                job.employment_type = EmploymentType(j.get("employment_type", "full_time"))
                job.summary = j.get("summary")
                job.is_technical = j.get("is_technical", True)
                job.sort_order = j.get("sort_order", 0)
                # Replace achievements
                for ach in list(job.achievements):
                    db.delete(ach)
                db.flush()
            else:
                job = Job(
                    title=j["title"],
                    company=j["company"],
                    location=j.get("location"),
                    start_date=_date(j["start_date"]),
                    end_date=_date(j.get("end_date")),
                    employment_type=EmploymentType(j.get("employment_type", "full_time")),
                    summary=j.get("summary"),
                    is_technical=j.get("is_technical", True),
                    sort_order=j.get("sort_order", 0),
                )
                db.add(job)
                db.flush()

            for idx, ach in enumerate(j.get("achievements", [])):
                tags = ach.get("impact_tags", [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
                db.add(
                    Achievement(
                        job_id=job.id,
                        text=ach["text"],
                        metric=ach.get("metric"),
                        impact_tags=tags,
                        prominence=ach.get("prominence", 3),
                        sort_order=idx,
                    )
                )
            for existing in list(job.job_skills):
                db.delete(existing)
            db.flush()
            for sk in j.get("skills", []):
                skill = skill_map.get(sk["name"])
                if not skill:
                    print(
                        f"  WARNING: skill '{sk['name']}' not found for {j['company']}/{j['title']}"
                    )
                    continue
                db.add(
                    JobSkill(
                        job_id=job.id,
                        skill_id=skill.id,
                        proficiency=sk.get("proficiency"),
                        years_used=sk.get("years_used"),
                    )
                )
                js_total += 1
            db.commit()
            job_map[(j["company"], j["title"])] = job
        print(f"  {len(data.get('jobs', []))} jobs seeded ({js_total} job_skill rows).")

        # Education
        for e in data.get("education", []):
            existing = (
                db.query(Education)
                .filter(Education.institution == e["institution"], Education.degree == e["degree"])
                .first()
            )
            if existing:
                edu = existing
            else:
                edu = Education(institution=e["institution"], degree=e["degree"], field=e["field"])
                db.add(edu)
            edu.field = e.get("field", edu.field)
            edu.location = e.get("location")
            edu.start_date = _date(e.get("start_date"))
            edu.end_date = _date(e.get("end_date"))
            edu.expected_end_date = _date(e.get("expected_end_date"))
            edu.is_in_progress = e.get("is_in_progress", False)
            edu.gpa = e.get("gpa")
            edu.honors = e.get("honors")
        db.commit()
        print(f"  {len(data.get('education', []))} education entries seeded.")

        # Certifications
        for c in data.get("certifications", []):
            existing = db.query(Certification).filter(Certification.name == c["name"]).first()
            if existing:
                cert = existing
            else:
                cert = Certification(name=c["name"], issuer=c["issuer"])
                db.add(cert)
            cert.issuer = c.get("issuer", cert.issuer)
            cert.issue_date = _date(c.get("issue_date"))
            cert.expiry_date = _date(c.get("expiry_date"))
            cert.credential_id = c.get("credential_id")
            cert.credential_url = c.get("credential_url")
            cert.notes = c.get("notes")
        db.commit()
        print(f"  {len(data.get('certifications', []))} certifications seeded.")

        # Projects
        for proj in data.get("projects", []):
            existing = db.query(Project).filter(Project.name == proj["name"]).first()
            if existing:
                p = existing
            else:
                p = Project(name=proj["name"], summary=proj["summary"])
                db.add(p)
            p.summary = proj.get("summary", p.summary)
            p.description = proj.get("description")
            p.repo_url = proj.get("repo_url")
            p.live_url = proj.get("live_url")
            p.start_date = _date(proj.get("start_date"))
            p.end_date = _date(proj.get("end_date"))
            p.is_active = proj.get("is_active", False)
            p.prominence = proj.get("prominence", 3)
            # Optional `job:` reference links the project to a specific job by
            # (company, title). If the lookup misses, leave job_id null and warn.
            job_ref = proj.get("job")
            if job_ref:
                linked = job_map.get((job_ref.get("company"), job_ref.get("title")))
                if linked:
                    p.job_id = linked.id
                else:
                    print(
                        f"  WARNING: project '{proj['name']}' references unknown " f"job: {job_ref}"
                    )
                    p.job_id = None
            else:
                p.job_id = None
        db.commit()
        print(f"  {len(data.get('projects', []))} projects seeded.")

    finally:
        db.close()

    print("Done.")


if __name__ == "__main__":
    seed_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/seed.yaml")
    if not seed_file.exists():
        print(f"Seed file not found: {seed_file}")
        print("Copy data/seed.yaml.example to data/seed.yaml and fill it in.")
        sys.exit(1)
    seed(seed_file)
