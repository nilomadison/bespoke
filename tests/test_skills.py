from src.models.skill import Skill


def test_list_skills_empty(client):
    response = client.get("/skills/")
    assert response.status_code == 200
    assert "No skills yet" in response.text


def test_create_skill_returns_row(client):
    response = client.post("/skills/", data={"name": "Python", "category": "Languages"})
    assert response.status_code == 200
    assert "Python" in response.text
    assert "Languages" in response.text


def test_skill_unique_constraint(client, db_session):
    db_session.add(Skill(name="Python", category="Languages"))
    db_session.commit()
    # Duplicate should raise — the route doesn't guard this, SQLAlchemy will raise
    import pytest
    with pytest.raises(Exception):
        client.post("/skills/", data={"name": "Python", "category": "Other"})


def test_get_skill_row(client, db_session):
    skill = Skill(name="Go", category="Languages")
    db_session.add(skill)
    db_session.commit()
    db_session.refresh(skill)

    response = client.get(f"/skills/{skill.id}")
    assert response.status_code == 200
    assert "Go" in response.text


def test_edit_skill_form(client, db_session):
    skill = Skill(name="TypeScript", category="Languages")
    db_session.add(skill)
    db_session.commit()
    db_session.refresh(skill)

    response = client.get(f"/skills/{skill.id}/edit")
    assert response.status_code == 200
    assert "TypeScript" in response.text


def test_update_skill(client, db_session):
    skill = Skill(name="Rust", category=None)
    db_session.add(skill)
    db_session.commit()
    db_session.refresh(skill)

    response = client.post(
        f"/skills/{skill.id}", data={"name": "Rust", "category": "Systems"}
    )
    assert response.status_code == 200
    assert "Systems" in response.text
    db_session.expire_all()
    updated = db_session.get(Skill, skill.id)
    assert updated.category == "Systems"


def test_delete_skill(client, db_session):
    skill = Skill(name="COBOL", category="Legacy")
    db_session.add(skill)
    db_session.commit()
    skill_id = skill.id

    response = client.post(f"/skills/{skill_id}/delete")
    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(Skill, skill_id) is None
