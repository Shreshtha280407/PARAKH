"""Human assessor scoring: GET/PUT /assessments/{id}/review and GET
/assessments/{id}/competency-profile. See server/app/routers/scoring.py.
"""
WT_HEADER = "X-Worker-Token"
A_PC = "CON/N0602.PC1"  # first task-evidenced PC, matches the fixture pack


def _assessment_in_review(client, imported_pack, worker, assessor_headers):
    a = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: a["worker_token"]})
    client.post(f"/assessments/{a['id']}/start-review", headers=assessor_headers)
    return a


def test_review_lists_all_71_rubric_items_unscored(client, imported_pack, worker, assessor_headers):
    a = _assessment_in_review(client, imported_pack, worker, assessor_headers)
    r = client.get(f"/assessments/{a['id']}/review", headers=assessor_headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 71
    assert all(item["score"] is None for item in items)


def test_review_requires_assessor_role(client, imported_pack, worker, assessor_headers):
    a = _assessment_in_review(client, imported_pack, worker, assessor_headers)
    r = client.get(f"/assessments/{a['id']}/review")
    assert r.status_code == 401


def test_put_score_demonstrated_computes_marks_and_requires_no_comment(client, imported_pack, worker, assessor_headers):
    a = _assessment_in_review(client, imported_pack, worker, assessor_headers)
    rubric = {item["pc_full_id"]: item for item in client.get(f"/assessments/{a['id']}/review", headers=assessor_headers).json()}
    max_marks = rubric[A_PC]["marks"]

    r = client.put(f"/assessments/{a['id']}/review", json={
        "pc_full_id": A_PC, "score_level": 3, "evidence_status": "DEMONSTRATED", "expected_version": 0,
    }, headers=assessor_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["marks_awarded"] == max_marks  # level 3/3 -- full marks
    assert body["version"] == 1
    assert body["scored_at"] is not None


def test_put_score_not_observed_requires_a_comment(client, imported_pack, worker, assessor_headers):
    a = _assessment_in_review(client, imported_pack, worker, assessor_headers)
    r = client.put(f"/assessments/{a['id']}/review", json={
        "pc_full_id": A_PC, "score_level": 0, "evidence_status": "NOT_OBSERVABLE", "expected_version": 0,
    }, headers=assessor_headers)
    assert r.status_code == 422

    r2 = client.put(f"/assessments/{a['id']}/review", json={
        "pc_full_id": A_PC, "score_level": 0, "evidence_status": "NOT_OBSERVABLE",
        "assessor_comment": "worker's shift ended before this task", "expected_version": 0,
    }, headers=assessor_headers)
    assert r2.status_code == 200, r2.text
    assert r2.json()["marks_awarded"] == "0.00"


def test_put_score_rejects_stale_version(client, imported_pack, worker, assessor_headers):
    a = _assessment_in_review(client, imported_pack, worker, assessor_headers)
    first = client.put(f"/assessments/{a['id']}/review", json={
        "pc_full_id": A_PC, "score_level": 2, "evidence_status": "DEMONSTRATED", "expected_version": 0,
    }, headers=assessor_headers)
    assert first.status_code == 200
    assert first.json()["version"] == 1

    # Retrying with the now-stale expected_version=0 must be rejected.
    stale = client.put(f"/assessments/{a['id']}/review", json={
        "pc_full_id": A_PC, "score_level": 3, "evidence_status": "DEMONSTRATED", "expected_version": 0,
    }, headers=assessor_headers)
    assert stale.status_code == 409

    # The correct next version succeeds and increments again.
    second = client.put(f"/assessments/{a['id']}/review", json={
        "pc_full_id": A_PC, "score_level": 3, "evidence_status": "DEMONSTRATED", "expected_version": 1,
    }, headers=assessor_headers)
    assert second.status_code == 200
    assert second.json()["version"] == 2


def test_put_score_rejected_outside_in_review_status(client, imported_pack, worker, assessor_headers):
    a = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()  # still draft
    r = client.put(f"/assessments/{a['id']}/review", json={
        "pc_full_id": A_PC, "score_level": 1, "evidence_status": "DEMONSTRATED", "expected_version": 0,
    }, headers=assessor_headers)
    assert r.status_code == 409


def test_competency_profile_is_decision_support_only_and_aggregates_correctly(client, imported_pack, worker, assessor_headers):
    a = _assessment_in_review(client, imported_pack, worker, assessor_headers)
    rubric = {item["pc_full_id"]: item for item in client.get(f"/assessments/{a['id']}/review", headers=assessor_headers).json()}
    max_marks = rubric[A_PC]["marks"]

    client.put(f"/assessments/{a['id']}/review", json={
        "pc_full_id": A_PC, "score_level": 3, "evidence_status": "DEMONSTRATED", "expected_version": 0,
    }, headers=assessor_headers)

    profile = client.get(f"/assessments/{a['id']}/competency-profile", headers=assessor_headers)
    assert profile.status_code == 200, profile.text
    body = profile.json()
    assert "Decision support only" in body["disclaimer"]
    assert "final certification/recommendation remains with the human assessor" in body["disclaimer"]
    assert body["pcs_scored"] == 1
    assert body["pcs_total"] == 71
    assert float(body["overall_marks_awarded"]) == float(max_marks)
    assert body["meets_minimum_threshold"] is False  # one PC out of 71 can't reach the pass threshold


def test_competency_profile_requires_assessor_role(client, imported_pack, worker, assessor_headers):
    a = _assessment_in_review(client, imported_pack, worker, assessor_headers)
    r = client.get(f"/assessments/{a['id']}/competency-profile")
    assert r.status_code == 401
    r2 = client.get(f"/assessments/{a['id']}/competency-profile", headers={WT_HEADER: a["worker_token"]})
    assert r2.status_code == 401
