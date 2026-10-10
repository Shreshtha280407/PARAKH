"""Assessment lifecycle state machine: draft -> submitted -> in_review ->
recommended/needs_reassessment (the decision transitions live in
test_decisions.py). See server/app/routers/assessments.py's submit_assessment
/ start_review and routers/uploads.py's require_draft evidence-locking.
"""
WT_HEADER = "X-Worker-Token"


def _new_assessment(client, imported_pack, worker):
    return client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()


def test_new_assessment_starts_in_draft(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    assert a["status"] == "draft"


def test_worker_can_submit_a_draft_assessment(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    r = client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: a["worker_token"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "submitted"
    assert body["submitted_at"] is not None


def test_submit_requires_the_assessments_own_worker_token(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    r = client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: "wrong-token"})
    assert r.status_code == 401
    r2 = client.post(f"/assessments/{a['id']}/submit")
    assert r2.status_code == 401


def test_submit_is_rejected_once_already_submitted(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    first = client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: token})
    assert first.status_code == 200
    second = client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: token})
    assert second.status_code == 409


def test_evidence_cannot_be_uploaded_after_submit(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: token})
    r = client.post("/uploads", json={
        "assessment_id": a["id"], "task_code": "T1", "kind": "photo", "mime": "image/jpeg", "claimed_size_bytes": 10,
    }, headers={WT_HEADER: token})
    assert r.status_code == 409


def test_chunk_put_is_rejected_after_submit_even_for_a_session_opened_before_it(client, imported_pack, worker):
    """A session opened while still draft must not accept further chunks
    once the assessment is submitted -- evidence-locking covers in-flight
    sessions too, not just new ones."""
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    opened = client.post("/uploads", json={
        "assessment_id": a["id"], "task_code": "T1", "kind": "photo", "mime": "image/jpeg", "claimed_size_bytes": 10,
    }, headers={WT_HEADER: token}).json()

    client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: token})

    r = client.put(f"/uploads/{opened['id']}/chunks/0", content=b"x" * 10, headers={WT_HEADER: token})
    assert r.status_code == 409


def test_assessor_can_start_review_on_a_submitted_assessment(client, imported_pack, worker, assessor_headers):
    a = _new_assessment(client, imported_pack, worker)
    client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: a["worker_token"]})
    r = client.post(f"/assessments/{a['id']}/start-review", headers=assessor_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "in_review"
    assert body["assessor_id"] is not None


def test_start_review_requires_assessor_role(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: a["worker_token"]})
    r = client.post(f"/assessments/{a['id']}/start-review")
    assert r.status_code == 401
    r2 = client.post(f"/assessments/{a['id']}/start-review", headers={WT_HEADER: a["worker_token"]})
    assert r2.status_code == 401


def test_start_review_rejected_while_still_draft(client, imported_pack, worker, assessor_headers):
    a = _new_assessment(client, imported_pack, worker)  # never submitted
    r = client.post(f"/assessments/{a['id']}/start-review", headers=assessor_headers)
    assert r.status_code == 409


def test_start_review_rejected_if_already_in_review(client, imported_pack, worker, assessor_headers):
    a = _new_assessment(client, imported_pack, worker)
    client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: a["worker_token"]})
    first = client.post(f"/assessments/{a['id']}/start-review", headers=assessor_headers)
    assert first.status_code == 200
    second = client.post(f"/assessments/{a['id']}/start-review", headers=assessor_headers)
    assert second.status_code == 409


def test_lifecycle_actions_are_recorded_in_the_audit_log(client, imported_pack, worker, assessor_headers, db_session):
    from server.app import models

    a = _new_assessment(client, imported_pack, worker)
    client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: a["worker_token"]})
    client.post(f"/assessments/{a['id']}/start-review", headers=assessor_headers)

    rows = db_session.query(models.AuditLog).filter_by(assessment_id=a["id"]).order_by(models.AuditLog.id).all()
    actions = [r.action for r in rows]
    assert actions == ["created", "submitted", "review_started"]
    assert rows[0].actor_role == "system"
    assert rows[1].actor_role == "worker" and rows[1].actor_user_id is None
    assert rows[2].actor_role == "assessor" and rows[2].actor_user_id is not None
