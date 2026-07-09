from datetime import date

from src.models.job import EmploymentType, Job


def _create_job(db_session) -> Job:
    job = Job(
        title="Software Engineer",
        company="Acme",
        start_date=date(2022, 1, 1),
        employment_type=EmploymentType.FULL_TIME,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def test_list_jobs_empty(client):
    response = client.get("/jobs/")
    assert response.status_code == 200
    assert "No jobs yet" in response.text


def test_list_jobs_with_data(client, db_session):
    _create_job(db_session)
    response = client.get("/jobs/")
    assert response.status_code == 200
    assert "Software Engineer" in response.text
    assert "Acme" in response.text


def test_new_job_form(client):
    response = client.get("/jobs/new")
    assert response.status_code == 200
    assert "<form" in response.text


def test_create_job_redirects(client):
    response = client.post(
        "/jobs/",
        data={
            "title": "ML Engineer",
            "company": "BestCo",
            "location": "Remote",
            "start_date": "2023-03-01",
            "end_date": "",
            "employment_type": "full_time",
            "summary": "Built ML pipelines.",
            "is_technical": "on",
            "sort_order": "0",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/jobs/"


def test_create_job_persists(client, db_session):
    client.post(
        "/jobs/",
        data={
            "title": "ML Engineer",
            "company": "BestCo",
            "location": "",
            "start_date": "2023-03-01",
            "end_date": "",
            "employment_type": "full_time",
            "summary": "",
            "is_technical": "on",
            "sort_order": "0",
        },
    )
    db_session.expire_all()
    job = db_session.query(Job).filter(Job.title == "ML Engineer").first()
    assert job is not None
    assert job.company == "BestCo"


def test_job_detail(client, db_session):
    job = _create_job(db_session)
    response = client.get(f"/jobs/{job.id}")
    assert response.status_code == 200
    assert "Software Engineer" in response.text
    assert "Achievements" in response.text


def test_edit_job_form(client, db_session):
    job = _create_job(db_session)
    response = client.get(f"/jobs/{job.id}/edit")
    assert response.status_code == 200
    assert "Software Engineer" in response.text


def test_update_job(client, db_session):
    job = _create_job(db_session)
    response = client.post(
        f"/jobs/{job.id}",
        data={
            "title": "Senior Software Engineer",
            "company": "Acme",
            "location": "NYC",
            "start_date": "2022-01-01",
            "end_date": "",
            "employment_type": "full_time",
            "summary": "Updated.",
            "is_technical": "on",
            "sort_order": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.expire_all()
    updated = db_session.get(Job, job.id)
    assert updated.title == "Senior Software Engineer"
    assert updated.sort_order == 1


def test_delete_job(client, db_session):
    job = _create_job(db_session)
    job_id = job.id
    response = client.post(f"/jobs/{job_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    db_session.expire_all()
    assert db_session.get(Job, job_id) is None


def test_delete_job_cascades_achievements(client, db_session):
    from src.models.achievement import Achievement

    job = _create_job(db_session)
    ach = Achievement(job_id=job.id, text="Did a thing", impact_tags=[], sort_order=0)
    db_session.add(ach)
    db_session.commit()
    ach_id = ach.id

    client.post(f"/jobs/{job.id}/delete")
    db_session.expire_all()
    assert db_session.get(Achievement, ach_id) is None
