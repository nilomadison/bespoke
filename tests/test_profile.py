def test_get_profile(client):
    response = client.get("/profile")
    assert response.status_code == 200
    assert "Test User" in response.text
    assert "test@example.com" in response.text


def test_update_profile(client, db_session):
    response = client.post(
        "/profile",
        data={
            "full_name": "Jane Smith",
            "email": "jane@example.com",
            "phone": "555-1234",
            "location": "SF, CA",
            "linkedin_url": "",
            "github_url": "",
            "portfolio_url": "",
            "baseline_summary": "Senior engineer.",
        },
    )
    assert response.status_code == 200
    assert "Jane Smith" in response.text
    assert "Saved" in response.text

    db_session.expire_all()
    from src.models.profile import Profile
    profile = db_session.get(Profile, 1)
    assert profile.full_name == "Jane Smith"
    assert profile.phone == "555-1234"
