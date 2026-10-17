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


# ---- cookie-based dashboard sessions + CSRF (P2.2 section 7) ----

def test_login_sets_an_httponly_access_token_cookie_and_a_readable_csrf_cookie(client, assessor):
    r = client.post("/auth/login", json={"email": assessor.email, "password": "correct horse battery staple"})
    assert r.status_code == 200
    set_cookie_headers = r.headers.get_list("set-cookie")
    access_cookie = next(h for h in set_cookie_headers if h.startswith("access_token="))
    csrf_cookie = next(h for h in set_cookie_headers if h.startswith("csrf_token="))
    assert "HttpOnly" in access_cookie
    assert "SameSite=lax" in access_cookie
    assert "HttpOnly" not in csrf_cookie  # the dashboard's JS must be able to read this one
    assert client.cookies.get("access_token") is not None
    assert client.cookies.get("csrf_token") is not None


def test_me_works_via_cookie_alone_with_no_bearer_header(client, assessor):
    client.post("/auth/login", json={"email": assessor.email, "password": "correct horse battery staple"})
    r = client.get("/auth/me")  # no Authorization header -- cookie jar supplies it
    assert r.status_code == 200
    assert r.json()["id"] == assessor.id


def test_mutating_cookie_request_without_csrf_header_is_rejected(client, assessor, imported_pack, worker):
    client.post("/auth/login", json={"email": assessor.email, "password": "correct horse battery staple"})
    a = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()

    r = client.post(f"/assessments/{a['id']}/worker-token/rotate")  # cookie auth, no X-CSRF-Token
    assert r.status_code == 403


def test_mutating_cookie_request_with_wrong_csrf_header_is_rejected(client, assessor, imported_pack, worker):
    client.post("/auth/login", json={"email": assessor.email, "password": "correct horse battery staple"})
    a = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()

    r = client.post(f"/assessments/{a['id']}/worker-token/rotate", headers={"X-CSRF-Token": "not-the-real-value"})
    assert r.status_code == 403


def test_mutating_cookie_request_with_correct_csrf_header_succeeds(client, assessor, imported_pack, worker):
    client.post("/auth/login", json={"email": assessor.email, "password": "correct horse battery staple"})
    a = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    csrf = client.cookies.get("csrf_token")

    r = client.post(f"/assessments/{a['id']}/worker-token/rotate", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text


def test_bearer_authenticated_mutating_request_never_needs_csrf(client, assessor_headers, imported_pack, worker):
    """A Bearer header can't be silently attached by a cross-site page, so
    the CSRF check only applies to the cookie path -- API clients/scripts
    using Authorization: Bearer are unaffected."""
    a = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    r = client.post(f"/assessments/{a['id']}/worker-token/rotate", headers=assessor_headers)
    assert r.status_code == 200, r.text


# ---- P10: naive per-process login throttle ----

def test_login_locks_out_after_too_many_failed_attempts(client, assessor):
    for _ in range(5):
        r = client.post("/auth/login", json={"email": assessor.email, "password": "wrong password"})
        assert r.status_code == 401
    # The 6th attempt is locked out before the password is even checked --
    # even the CORRECT password must not succeed while locked out.
    r = client.post("/auth/login", json={"email": assessor.email, "password": "correct horse battery staple"})
    assert r.status_code == 429


def test_login_lockout_is_per_email_not_global(client, assessor):
    for _ in range(5):
        client.post("/auth/login", json={"email": assessor.email, "password": "wrong password"})
    # A different email is unaffected by another account's lockout.
    r = client.post("/auth/login", json={"email": "nobody@test.local", "password": "anything"})
    assert r.status_code == 401  # unknown user, not 429


def test_successful_login_clears_the_failed_attempt_counter(client, assessor):
    for _ in range(4):
        client.post("/auth/login", json={"email": assessor.email, "password": "wrong password"})
    r = client.post("/auth/login", json={"email": assessor.email, "password": "correct horse battery staple"})
    assert r.status_code == 200
    # Back under the threshold -- a fresh wrong attempt is a normal 401, not 429.
    r = client.post("/auth/login", json={"email": assessor.email, "password": "wrong password"})
    assert r.status_code == 401


def test_logout_clears_cookies_and_ends_the_session(client, assessor):
    client.post("/auth/login", json={"email": assessor.email, "password": "correct horse battery staple"})
    assert client.get("/auth/me").status_code == 200

    r = client.post("/auth/logout")
    assert r.status_code == 200
    assert client.cookies.get("access_token") is None

    assert client.get("/auth/me").status_code == 401
