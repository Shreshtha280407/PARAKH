def test_create_assessment_seeds_fixed_five_tasks_in_order_and_returns_a_worker_token(client, imported_pack, worker):
    r = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id})
    assert r.status_code == 201
    body = r.json()
    assert [t["task_code"] for t in body["tasks"]] == ["T1", "T2", "T3", "T4", "T5"]
    assert [t["budget_bytes"] for t in body["tasks"]] == [
        15 * 1024 * 1024, 20 * 1024 * 1024, 30 * 1024 * 1024, 25 * 1024 * 1024, 30 * 1024 * 1024,
    ]
    assert len(body["worker_token"]) > 20


def test_each_assessment_gets_a_distinct_worker_token(client, imported_pack, worker):
    a = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    b = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    assert a["worker_token"] != b["worker_token"]


def test_create_assessment_rejects_unknown_worker(client, imported_pack):
    r = client.post("/assessments", json={"worker_id": 999999, "pack_id": imported_pack.id})
    assert r.status_code == 404


def test_get_assessment_with_correct_worker_token_succeeds(client, imported_pack, worker):
    created = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    r = client.get(f"/assessments/{created['id']}", headers={"X-Worker-Token": created["worker_token"]})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == created["id"]
    assert body["pack_code"] == "CON/Q0602"
    assert body["worker_name"] == worker.display_name
    assert body["total_budget_bytes"] == 120 * 1024 * 1024
    assert body["tasks"][0]["evidence"] == []  # no uploads yet -- empty, not missing


def test_get_assessment_with_wrong_worker_token_is_rejected(client, imported_pack, worker):
    created = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    r = client.get(f"/assessments/{created['id']}", headers={"X-Worker-Token": "not-the-right-token"})
    assert r.status_code == 401


def test_get_assessment_with_no_credentials_is_rejected(client, imported_pack, worker):
    created = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    r = client.get(f"/assessments/{created['id']}")
    assert r.status_code == 401


def test_get_assessment_with_another_assessments_worker_token_is_rejected(client, imported_pack, worker):
    """A worker token only ever opens its OWN assessment, not a sibling one."""
    a = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    b = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    r = client.get(f"/assessments/{a['id']}", headers={"X-Worker-Token": b["worker_token"]})
    assert r.status_code == 401


def test_get_assessment_with_assessor_token_succeeds(client, imported_pack, worker, assessor_headers):
    created = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    r = client.get(f"/assessments/{created['id']}", headers=assessor_headers)
    assert r.status_code == 200


def test_get_assessment_with_assessor_session_cookie_succeeds(client, imported_pack, worker, assessor):
    """_assessor_or_worker_token must accept the dashboard's cookie-based
    session, not just a Bearer header -- found via live browser testing:
    the cookie path was wired into auth.get_current_user but this
    endpoint's separate dependency didn't know about it yet."""
    created = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    login = client.post("/auth/login", json={"email": assessor.email, "password": "correct horse battery staple"})
    assert login.status_code == 200

    r = client.get(f"/assessments/{created['id']}")  # no Authorization header -- cookie jar supplies it
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_assessment_with_token_for_deleted_assessor_is_rejected(
    client, imported_pack, worker, assessor, assessor_token, db_session
):
    """A JWT's role claim is a snapshot from login time -- if the user is
    deleted afterward, access must be revoked immediately, not whenever the
    token happens to expire (see routers/assessments.py's
    _assessor_or_worker_token, which re-checks the live DB row)."""
    created = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    db_session.delete(assessor)
    db_session.commit()
    r = client.get(f"/assessments/{created['id']}", headers={"Authorization": f"Bearer {assessor_token}"})
    assert r.status_code == 401


def test_get_assessment_with_token_for_demoted_assessor_is_rejected(
    client, imported_pack, worker, assessor, assessor_token, db_session
):
    """Same as above, but demoted rather than deleted -- the JWT still
    claims role=assessor, but the live DB row says otherwise."""
    created = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    assessor.role = "worker"
    db_session.commit()
    r = client.get(f"/assessments/{created['id']}", headers={"Authorization": f"Bearer {assessor_token}"})
    assert r.status_code == 401


def test_assessment_rubric_requires_assessor_role(client, imported_pack, worker):
    created = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    r = client.get(f"/assessments/{created['id']}/rubric")
    assert r.status_code == 401
    r2 = client.get(f"/assessments/{created['id']}/rubric", headers={"X-Worker-Token": created["worker_token"]})
    assert r2.status_code == 401  # a worker token is not an assessor bearer token


def test_assessment_rubric_returns_71_task_evidenced_pcs_with_decimal_marks(client, imported_pack, worker, assessor_headers):
    created = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    r = client.get(f"/assessments/{created['id']}/rubric", headers=assessor_headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 71
    marks = {item["marks"] for item in items}
    assert "5.83" in marks


def test_worker_role_jwt_cannot_access_assessor_rubric_endpoint(client, imported_pack, worker, db_session):
    """A valid token with the wrong role gets 403, not 401."""
    from server.app.auth import create_access_token

    created = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    # Workers never normally get a JWT (no login) -- this simulates "a
    # valid token exists but the role is insufficient" to prove the server
    # checks role, not just token validity.
    worker.role = "worker"
    token = create_access_token(worker)
    r = client.get(f"/assessments/{created['id']}/rubric", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
