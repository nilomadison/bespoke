from datetime import date

from src.models.achievement import Achievement
from src.models.job import EmploymentType, Job


def _setup(db_session):
    job = Job(
        title="Engineer",
        company="Corp",
        start_date=date(2021, 1, 1),
        employment_type=EmploymentType.FULL_TIME,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def test_create_achievement_returns_row_fragment(client, db_session):
    job = _setup(db_session)
    response = client.post(
        f"/jobs/{job.id}/achievements/",
        data={
            "text": "Reduced latency by 40%",
            "metric": "40% improvement",
            "impact_tags": "scale, reliability",
            "sort_order": "0",
        },
    )
    assert response.status_code == 200
    assert "Reduced latency" in response.text
    assert "40% improvement" in response.text
    assert "scale" in response.text


def test_achievement_persists_with_tags(client, db_session):
    job = _setup(db_session)
    client.post(
        f"/jobs/{job.id}/achievements/",
        data={
            "text": "Led migration project",
            "metric": "",
            "impact_tags": "leadership, architecture",
            "sort_order": "0",
        },
    )
    db_session.expire_all()
    ach = db_session.query(Achievement).filter(Achievement.job_id == job.id).first()
    assert ach is not None
    assert ach.text == "Led migration project"
    assert "leadership" in ach.impact_tags
    assert "architecture" in ach.impact_tags


def test_get_achievement_row(client, db_session):
    job = _setup(db_session)
    ach = Achievement(job_id=job.id, text="Did something", impact_tags=["scale"], sort_order=0)
    db_session.add(ach)
    db_session.commit()
    db_session.refresh(ach)

    response = client.get(f"/jobs/{job.id}/achievements/{ach.id}")
    assert response.status_code == 200
    assert "Did something" in response.text


def test_edit_achievement_form(client, db_session):
    job = _setup(db_session)
    ach = Achievement(job_id=job.id, text="Built a feature", impact_tags=[], sort_order=0)
    db_session.add(ach)
    db_session.commit()
    db_session.refresh(ach)

    response = client.get(f"/jobs/{job.id}/achievements/{ach.id}/edit")
    assert response.status_code == 200
    assert "Built a feature" in response.text
    assert "<form" in response.text


def test_update_achievement(client, db_session):
    job = _setup(db_session)
    ach = Achievement(job_id=job.id, text="Old text", impact_tags=["cost"], sort_order=0)
    db_session.add(ach)
    db_session.commit()
    db_session.refresh(ach)

    response = client.post(
        f"/jobs/{job.id}/achievements/{ach.id}",
        data={
            "text": "New text",
            "metric": "Saved $1M",
            "impact_tags": "cost_reduction",
            "sort_order": "0",
        },
    )
    assert response.status_code == 200
    assert "New text" in response.text
    db_session.expire_all()
    updated = db_session.get(Achievement, ach.id)
    assert updated.text == "New text"


def test_delete_achievement(client, db_session):
    job = _setup(db_session)
    ach = Achievement(job_id=job.id, text="To delete", impact_tags=[], sort_order=0)
    db_session.add(ach)
    db_session.commit()
    ach_id = ach.id

    response = client.post(f"/jobs/{job.id}/achievements/{ach_id}/delete")
    assert response.status_code == 200
    assert response.text == ""
    db_session.expire_all()
    assert db_session.get(Achievement, ach_id) is None
