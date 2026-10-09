def test_login_succeeds_with_correct_credentials(client, assessor):
    r = client.post("/auth/login", json={"email": assessor.email, "password": "correct horse battery staple"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20
    assert body["expires_in_minutes"] == 60


def test_login_fails_with_wrong_password(client, assessor):
    r = client.post("/auth/login", json={"email": assessor.email, "password": "wrong password"})
    assert r.status_code == 401


def test_login_fails_for_unknown_email(client):
    r = client.post("/auth/login", json={"email": "nobody@test.local", "password": "anything"})
    assert r.status_code == 401


def test_login_fails_for_worker_role_even_with_a_password_hash(client, db_session):
    from server.app import models
    from server.app.auth import hash_password

    # A worker somehow has a password_hash set -- login must still refuse,
    # workers are not allowed to use this endpoint at all.
    w = models.User(
        role="worker", display_name="W", phone="9000000099",
        email="worker-with-a-hash@test.local", password_hash=hash_password("x"),
    )
    db_session.add(w)
    db_session.commit()

    r = client.post("/auth/login", json={"email": w.email, "password": "x"})
    assert r.status_code == 401


def test_me_requires_a_token(client):
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_me_returns_the_authenticated_assessor(client, assessor, assessor_headers):
    r = client.get("/auth/me", headers=assessor_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == assessor.id
    assert body["role"] == "assessor"


def test_me_rejects_a_garbage_token(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_response_never_includes_password_hash(client, assessor, assessor_headers):
    r = client.get("/auth/me", headers=assessor_headers)
    assert "password" not in r.text.lower()
