"""Recommendation sign-off (POST /assessments/{id}/decision) and
reassessment (POST /assessments/{id}/reassess). See
server/app/routers/decisions.py.
"""
WT_HEADER = "X-Worker-Token"


def _assessment_in_review(client, imported_pack, worker, assessor_headers):
    a = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: a["worker_token"]})
    client.post(f"/assessments/{a['id']}/start-review", headers=assessor_headers)
    return a


def test_decision_recommended_transitions_status(client, imported_pack, worker, assessor_headers):
    a = _assessment_in_review(client, imported_pack, worker, assessor_headers)
    r = client.post(f"/assessments/{a['id']}/decision", json={"decision": "recommended", "notes": "all good"}, headers=assessor_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "recommended"
    assert body["decision"] == "recommended"
    assert body["decision_notes"] == "all good"


def test_decision_needs_reassessment_transitions_status(client, imported_pack, worker, assessor_headers):
    a = _assessment_in_review(client, imported_pack, worker, assessor_headers)
    r = client.post(
        f"/assessments/{a['id']}/decision",
        json={"decision": "needs_reassessment", "notes": "T3 evidence insufficient"},
        headers=assessor_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "needs_reassessment"


def test_decision_requires_assessor_role(client, imported_pack, worker, assessor_headers):
    a = _assessment_in_review(client, imported_pack, worker, assessor_headers)
    r = client.post(f"/assessments/{a['id']}/decision", json={"decision": "recommended"})
    assert r.status_code == 401


def test_decision_rejected_outside_in_review(client, imported_pack, worker, assessor_headers):
    a = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()  # draft
    r = client.post(f"/assessments/{a['id']}/decision", json={"decision": "recommended"}, headers=assessor_headers)
    assert r.status_code == 409


def test_decision_rejects_invalid_value(client, imported_pack, worker, assessor_headers):
    a = _assessment_in_review(client, imported_pack, worker, assessor_headers)
    r = client.post(f"/assessments/{a['id']}/decision", json={"decision": "approved"}, headers=assessor_headers)
    assert r.status_code == 422


def test_reassess_creates_a_fresh_assessment_with_a_new_token(client, imported_pack, worker, assessor_headers):
    a = _assessment_in_review(client, imported_pack, worker, assessor_headers)
    client.post(f"/assessments/{a['id']}/decision", json={"decision": "needs_reassessment"}, headers=assessor_headers)

    r = client.post(f"/assessments/{a['id']}/reassess", headers=assessor_headers)
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["id"] != a["id"]
    assert new["worker_token"] != a["worker_token"]
    assert new["status"] == "draft"
    assert [t["task_code"] for t in new["tasks"]] == ["T1", "T2", "T3", "T4", "T5"]


def test_reassess_leaves_the_original_assessment_untouched(client, imported_pack, worker, assessor_headers):
    import hashlib

    a = _assessment_in_review(client, imported_pack, worker, assessor_headers)
    rubric = client.get(f"/assessments/{a['id']}/review", headers=assessor_headers).json()
    pc = rubric[0]["pc_full_id"]
    client.put(f"/assessments/{a['id']}/review", json={
        "pc_full_id": pc, "score_level": 2, "evidence_status": "DEMONSTRATED", "expected_version": 0,
    }, headers=assessor_headers)
    client.post(f"/assessments/{a['id']}/decision", json={"decision": "needs_reassessment", "notes": "redo T2"}, headers=assessor_headers)

    before = client.get(f"/assessments/{a['id']}", headers=assessor_headers).json()
    client.post(f"/assessments/{a['id']}/reassess", headers=assessor_headers)
    after = client.get(f"/assessments/{a['id']}", headers=assessor_headers).json()

    assert before == after  # completely untouched by creating the reassessment
    assert after["status"] == "needs_reassessment"
    assert after["decision_notes"] == "redo T2"
    scores_after = client.get(f"/assessments/{a['id']}/review", headers=assessor_headers).json()
    scored = next(item for item in scores_after if item["pc_full_id"] == pc)
    assert scored["score"]["score_level"] == 2  # the original score survives


def test_reassess_links_back_to_the_original_via_reassessment_of_id(client, imported_pack, worker, assessor_headers):
    a = _assessment_in_review(client, imported_pack, worker, assessor_headers)
    client.post(f"/assessments/{a['id']}/decision", json={"decision": "needs_reassessment"}, headers=assessor_headers)
    new = client.post(f"/assessments/{a['id']}/reassess", headers=assessor_headers).json()

    detail = client.get(f"/assessments/{new['id']}", headers={WT_HEADER: new["worker_token"]}).json()
    assert detail["reassessment_of_id"] == a["id"]


def test_reassess_rejected_unless_needs_reassessment(client, imported_pack, worker, assessor_headers):
    a = _assessment_in_review(client, imported_pack, worker, assessor_headers)  # in_review, no decision yet
    r = client.post(f"/assessments/{a['id']}/reassess", headers=assessor_headers)
    assert r.status_code == 409


def test_reassess_requires_assessor_role(client, imported_pack, worker, assessor_headers):
    a = _assessment_in_review(client, imported_pack, worker, assessor_headers)
    client.post(f"/assessments/{a['id']}/decision", json={"decision": "needs_reassessment"}, headers=assessor_headers)
    r = client.post(f"/assessments/{a['id']}/reassess")
    assert r.status_code == 401
