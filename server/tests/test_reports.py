"""Tamper-evident signed reports -- see server/app/report_signing.py and
routers/reports.py.
"""
WT_HEADER = "X-Worker-Token"


def _recommended_assessment(client, imported_pack, worker, assessor_headers):
    a = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: a["worker_token"]})
    client.post(f"/assessments/{a['id']}/start-review", headers=assessor_headers)
    rubric = client.get(f"/assessments/{a['id']}/review", headers=assessor_headers).json()
    client.put(f"/assessments/{a['id']}/review", json={
        "pc_full_id": rubric[0]["pc_full_id"], "score_level": 3, "evidence_status": "DEMONSTRATED", "expected_version": 0,
    }, headers=assessor_headers)
    client.post(f"/assessments/{a['id']}/decision", json={"decision": "recommended", "notes": "looks good"}, headers=assessor_headers)
    return a


def test_generate_report_requires_a_decision(client, imported_pack, worker, assessor_headers):
    a = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: a["worker_token"]})
    client.post(f"/assessments/{a['id']}/start-review", headers=assessor_headers)  # in_review, no decision
    r = client.post(f"/assessments/{a['id']}/report", headers=assessor_headers)
    assert r.status_code == 409


def test_generate_report_requires_assessor_role(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    r = client.post(f"/assessments/{a['id']}/report")
    assert r.status_code == 401


def test_generate_report_succeeds_and_is_idempotent(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    first = client.post(f"/assessments/{a['id']}/report", headers=assessor_headers)
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["assessment_id"] == a["id"]
    assert len(body["sha256"]) == 64
    assert len(body["signature"]) == 128  # Ed25519 signature, 64 bytes hex-encoded

    second = client.post(f"/assessments/{a['id']}/report", headers=assessor_headers)
    assert second.status_code == 201
    assert second.json() == body  # same signed artifact, not regenerated


def test_download_report_json_matches_signed_hash(client, imported_pack, worker, assessor_headers):
    import hashlib

    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    signed = client.post(f"/assessments/{a['id']}/report", headers=assessor_headers).json()

    r = client.get(f"/assessments/{a['id']}/report", headers=assessor_headers)
    assert r.status_code == 200
    assert hashlib.sha256(r.content).hexdigest() == signed["sha256"]


def test_download_report_pdf(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    client.post(f"/assessments/{a['id']}/report", headers=assessor_headers)
    r = client.get(f"/assessments/{a['id']}/report", params={"format": "pdf"}, headers=assessor_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_download_report_accessible_by_the_assessments_own_worker_token(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    client.post(f"/assessments/{a['id']}/report", headers=assessor_headers)
    r = client.get(f"/assessments/{a['id']}/report", headers={WT_HEADER: a["worker_token"]})
    assert r.status_code == 200


def test_download_report_rejects_a_strangers_worker_token(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    client.post(f"/assessments/{a['id']}/report", headers=assessor_headers)
    other = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    r = client.get(f"/assessments/{a['id']}/report", headers={WT_HEADER: other["worker_token"]})
    assert r.status_code == 401


def test_verify_endpoint_is_public_and_confirms_a_valid_report(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    client.post(f"/assessments/{a['id']}/report", headers=assessor_headers)

    r = client.get(f"/reports/{a['id']}/verify")  # no auth headers at all
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True
    assert body["assessment_id"] == a["id"]
    assert "key_id" in body
    # Never exposes report content/evidence -- just the verdict + metadata.
    assert "canonical_json" not in body and "criteria" not in body and "scores" not in body


def test_verify_detects_tampering_with_the_stored_report(client, imported_pack, worker, assessor_headers, db_session):
    """The actual tamper-evidence proof: mutate the stored canonical_json
    (as if an attacker with DB write access altered a score after the fact)
    and confirm verify flips from valid to invalid."""
    from server.app import models

    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    client.post(f"/assessments/{a['id']}/report", headers=assessor_headers)

    before = client.get(f"/reports/{a['id']}/verify")
    assert before.json()["valid"] is True

    report = db_session.query(models.SignedReport).filter_by(assessment_id=a["id"]).one()
    report.canonical_json = report.canonical_json.replace('"overall_percent":', '"overall_percent":999,"x":')
    db_session.commit()

    after = client.get(f"/reports/{a['id']}/verify")
    assert after.status_code == 200
    assert after.json()["valid"] is False


def test_verify_for_a_nonexistent_report_is_404(client, imported_pack, worker):
    a = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    r = client.get(f"/reports/{a['id']}/verify")
    assert r.status_code == 404
