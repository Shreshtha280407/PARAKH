"""Worker capability token rotation/revocation -- see
server/app/routers/tokens.py and docs/worker_capability_tokens.md.
"""
WT_HEADER = "X-Worker-Token"


def _new_assessment(client, imported_pack, worker):
    return client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()


def test_rotate_issues_a_new_token_and_invalidates_the_old_one(client, imported_pack, worker, assessor_headers):
    a = _new_assessment(client, imported_pack, worker)
    old_token = a["worker_token"]

    r = client.post(f"/assessments/{a['id']}/worker-token/rotate", headers=assessor_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "active"
    new_token = body["worker_token"]
    assert new_token != old_token

    old = client.get(f"/assessments/{a['id']}", headers={WT_HEADER: old_token})
    assert old.status_code == 401

    new = client.get(f"/assessments/{a['id']}", headers={WT_HEADER: new_token})
    assert new.status_code == 200


def test_rotate_requires_assessor_role(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    r = client.post(f"/assessments/{a['id']}/worker-token/rotate", headers={WT_HEADER: a["worker_token"]})
    assert r.status_code == 401


def test_revoke_disables_the_worker_token_everywhere(client, imported_pack, worker, assessor_headers):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]

    r = client.post(f"/assessments/{a['id']}/worker-token/revoke", headers=assessor_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "revoked"
    assert r.json()["worker_token"] is None

    get_r = client.get(f"/assessments/{a['id']}", headers={WT_HEADER: token})
    assert get_r.status_code == 401

    upload_r = client.post("/uploads", json={
        "assessment_id": a["id"], "task_code": "T1", "kind": "photo", "mime": "image/jpeg", "claimed_size_bytes": 10,
    }, headers={WT_HEADER: token})
    assert upload_r.status_code == 401

    submit_r = client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: token})
    assert submit_r.status_code == 401


def test_revoke_requires_assessor_role(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    r = client.post(f"/assessments/{a['id']}/worker-token/revoke", headers={WT_HEADER: a["worker_token"]})
    assert r.status_code == 401


def test_rotate_after_revoke_reactivates_with_a_fresh_token(client, imported_pack, worker, assessor_headers):
    a = _new_assessment(client, imported_pack, worker)
    client.post(f"/assessments/{a['id']}/worker-token/revoke", headers=assessor_headers)

    r = client.post(f"/assessments/{a['id']}/worker-token/rotate", headers=assessor_headers)
    assert r.status_code == 200
    new_token = r.json()["worker_token"]

    get_r = client.get(f"/assessments/{a['id']}", headers={WT_HEADER: new_token})
    assert get_r.status_code == 200


def test_token_actions_are_audited(client, imported_pack, worker, assessor_headers, db_session):
    from server.app import models

    a = _new_assessment(client, imported_pack, worker)
    client.post(f"/assessments/{a['id']}/worker-token/rotate", headers=assessor_headers)
    client.post(f"/assessments/{a['id']}/worker-token/revoke", headers=assessor_headers)

    actions = [
        row.action for row in
        db_session.query(models.AuditLog).filter_by(assessment_id=a["id"]).order_by(models.AuditLog.id).all()
    ]
    assert actions == ["created", "token_rotated", "token_revoked"]
