"""Tamper-evident signed reports -- P7 redesign: password-confirmed
sign-off, PDF-bytes-first Ed25519 signing, immutable stored artifact,
public /verify/{report_id}. See server/app/report_signing.py,
routers/reports.py, routers/verify.py, docs/gates/P7.md sections 4-5.
"""
WT_HEADER = "X-Worker-Token"
ASSESSOR_PASSWORD = "correct horse battery staple"  # matches conftest.assessor


def _score_all_pcs(client, assessment_id, headers, level=3, evidence_status="DEMONSTRATED", comment=None):
    items = client.get(f"/assessments/{assessment_id}/review", headers=headers).json()
    for item in items:
        body = {
            "pc_full_id": item["pc_full_id"], "score_level": level,
            "evidence_status": evidence_status, "expected_version": 0,
        }
        if evidence_status != "DEMONSTRATED" or comment:
            body["assessor_comment"] = comment or "test comment"
        r = client.put(f"/assessments/{assessment_id}/review", json=body, headers=headers)
        assert r.status_code == 200, r.text


def _in_review_assessment(client, imported_pack, worker, assessor_headers):
    a = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: a["worker_token"]})
    client.post(f"/assessments/{a['id']}/start-review", headers=assessor_headers)
    return a


def _recommended_assessment(client, imported_pack, worker, assessor_headers):
    """Every mandatory PC scored at level 3 -- a genuine RECOMMEND_CERTIFICATION."""
    a = _in_review_assessment(client, imported_pack, worker, assessor_headers)
    _score_all_pcs(client, a["id"], assessor_headers, level=3)
    return a


def _sign_off(client, assessment_id, headers, final_recommendation="RECOMMEND_CERTIFICATION", override_reason=None, password=ASSESSOR_PASSWORD):
    body = {"password": password, "final_recommendation": final_recommendation}
    if override_reason is not None:
        body["override_reason"] = override_reason
    return client.post(f"/assessments/{assessment_id}/sign-off", json=body, headers=headers)


def test_sign_off_requires_in_review(client, imported_pack, worker, assessor_headers):
    a = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: a["worker_token"]})  # submitted, not in_review
    r = _sign_off(client, a["id"], assessor_headers)
    assert r.status_code == 409


def test_sign_off_requires_assessor_role(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    r = client.post(f"/assessments/{a['id']}/sign-off", json={"password": ASSESSOR_PASSWORD, "final_recommendation": "RECOMMEND_CERTIFICATION"})
    assert r.status_code == 401


def test_sign_off_wrong_password_rejected(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    r = _sign_off(client, a["id"], assessor_headers, password="definitely not the password")
    assert r.status_code == 401
    # And the assessment must NOT have been signed/advanced.
    detail = client.get(f"/assessments/{a['id']}", headers=assessor_headers).json()
    assert detail["status"] == "in_review"


def test_sign_off_rejects_wrong_role_even_with_correct_admin_password(client, imported_pack, worker, assessor_headers, admin, admin_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    r = _sign_off(client, a["id"], admin_headers, password="another strong passphrase")
    assert r.status_code == 201  # admin is an authorised role with its own correct password -- this one succeeds
    # A SEPARATE assessment, signed off by the admin using the ASSESSOR's password, must fail --
    # proves the password is checked against the AUTHENTICATED caller, not just "some valid password".
    b = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    r2 = _sign_off(client, b["id"], admin_headers, password=ASSESSOR_PASSWORD)
    assert r2.status_code == 401


def test_sign_off_missing_override_reason_when_recommendation_differs_is_422(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)  # computed = RECOMMEND_CERTIFICATION
    r = _sign_off(client, a["id"], assessor_headers, final_recommendation="NOT_YET_COMPETENT")
    assert r.status_code == 422


def test_sign_off_whitespace_only_override_reason_is_422(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    r = _sign_off(client, a["id"], assessor_headers, final_recommendation="NOT_YET_COMPETENT", override_reason="   ")
    assert r.status_code == 422


def test_sign_off_with_valid_override_reason_succeeds_and_persists_reason(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    r = _sign_off(
        client, a["id"], assessor_headers, final_recommendation="NOT_YET_COMPETENT",
        override_reason="Assessor judgement: evidence looks rehearsed, not convinced despite scores.",
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["computed_recommendation"] == "RECOMMEND_CERTIFICATION"
    assert body["final_recommendation"] == "NOT_YET_COMPETENT"
    assert "rehearsed" in body["override_reason"]


def test_sign_off_succeeds_and_is_idempotent(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    first = _sign_off(client, a["id"], assessor_headers)
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["assessment_id"] == a["id"]
    assert len(body["pdf_sha256"]) == 64
    assert len(body["signature"]) == 128  # Ed25519 signature, 64 bytes hex-encoded
    assert body["report_uid"]

    second = _sign_off(client, a["id"], assessor_headers)
    assert second.status_code == 201
    assert second.json() == body  # same signed artifact, never resigned

    detail = client.get(f"/assessments/{a['id']}", headers=assessor_headers).json()
    assert detail["status"] == "recommended"


def test_sign_off_blocked_while_a_reassessment_request_is_pending(client, imported_pack, worker, assessor_headers):
    a = _in_review_assessment(client, imported_pack, worker, assessor_headers)
    _score_all_pcs(client, a["id"], assessor_headers, level=3)
    client.post(f"/assessments/{a['id']}/reassessment-requests", json={
        "task_codes": ["T4"], "reason": "evidence unclear", "capture_instructions": "retake T4 wider angle",
    }, headers=assessor_headers)
    # status is now needs_reassessment, so sign-off's own in_review gate already blocks it (409) --
    # this is the structural enforcement of "signing blocked while reassessment incomplete".
    r = _sign_off(client, a["id"], assessor_headers)
    assert r.status_code == 409


def test_critical_pc_at_level_1_forces_not_yet_competent_by_default(client, imported_pack, worker, assessor_headers):
    a = _in_review_assessment(client, imported_pack, worker, assessor_headers)
    _score_all_pcs(client, a["id"], assessor_headers, level=3)
    items = client.get(f"/assessments/{a['id']}/review", headers=assessor_headers).json()
    critical_item = next(i for i in items if i["critical"])
    client.put(f"/assessments/{a['id']}/review", json={
        "pc_full_id": critical_item["pc_full_id"], "score_level": 1,
        "evidence_status": "DEMONSTRATED", "expected_version": critical_item["score"]["version"],
    }, headers=assessor_headers)

    profile = client.get(f"/assessments/{a['id']}/competency-profile", headers=assessor_headers).json()
    assert profile["computed_outcome"] == "NOT_YET_COMPETENT"
    assert critical_item["pc_full_id"] in profile["critical_violation_pc_ids"]

    # Signing WITH the computed (NOT_YET_COMPETENT) value needs no override reason.
    r = _sign_off(client, a["id"], assessor_headers, final_recommendation="NOT_YET_COMPETENT")
    assert r.status_code == 201, r.text
    assert r.json()["final_recommendation"] == "NOT_YET_COMPETENT"

    pdf = client.get(f"/assessments/{a['id']}/report", params={"format": "pdf"}, headers=assessor_headers)
    assert critical_item["pc_full_id"].encode() in pdf.content  # the critical PC appears in the signed PDF


def test_download_report_json(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    _sign_off(client, a["id"], assessor_headers)
    r = client.get(f"/assessments/{a['id']}/report", headers=assessor_headers)
    assert r.status_code == 200
    assert r.json()["assessment_id"] == a["id"]


def test_download_report_pdf_has_required_content(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    _sign_off(client, a["id"], assessor_headers)
    r = client.get(f"/assessments/{a['id']}/report", params={"format": "pdf"}, headers=assessor_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    assert b"Assessor recommendation" in r.content
    assert b"not an official certificate" in r.content


def test_download_report_pdf_is_the_stored_bytes_not_a_rerender(client, imported_pack, worker, assessor_headers):
    """Two downloads must be byte-identical -- proves it's a stored
    artifact, not re-rendered (which could legitimately differ run to run,
    e.g. a timestamp baked into a fresh render)."""
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    _sign_off(client, a["id"], assessor_headers)
    first = client.get(f"/assessments/{a['id']}/report", params={"format": "pdf"}, headers=assessor_headers).content
    second = client.get(f"/assessments/{a['id']}/report", params={"format": "pdf"}, headers=assessor_headers).content
    assert first == second


def test_download_report_receipt_has_detached_signature_fields(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    signed = _sign_off(client, a["id"], assessor_headers).json()
    r = client.get(f"/assessments/{a['id']}/report", params={"format": "receipt"}, headers=assessor_headers)
    assert r.status_code == 200
    receipt = r.json()
    assert receipt["pdf_sha256"] == signed["pdf_sha256"]
    assert receipt["signature"] == signed["signature"]
    assert receipt["key_id"] == signed["key_id"]
    assert receipt["report_id"] == signed["report_uid"]


def test_download_report_accessible_by_the_assessments_own_worker_token(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    _sign_off(client, a["id"], assessor_headers)
    r = client.get(f"/assessments/{a['id']}/report", headers={WT_HEADER: a["worker_token"]})
    assert r.status_code == 200


def test_download_report_rejects_a_strangers_worker_token(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    _sign_off(client, a["id"], assessor_headers)
    other = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    r = client.get(f"/assessments/{a['id']}/report", headers={WT_HEADER: other["worker_token"]})
    assert r.status_code == 401


def test_legacy_assessment_id_verify_endpoint_is_public_and_confirms_a_valid_report(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    _sign_off(client, a["id"], assessor_headers)

    r = client.get(f"/reports/{a['id']}/verify")  # no auth headers at all
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True
    assert body["assessment_id"] == a["id"]
    assert "key_id" in body
    assert "canonical_json" not in body and "criteria" not in body and "evidence" not in body


def test_legacy_verify_for_a_nonexistent_report_is_404(client, imported_pack, worker):
    a = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    r = client.get(f"/reports/{a['id']}/verify")
    assert r.status_code == 404


def test_public_verify_by_report_id_exposes_only_minimal_safe_fields(client, imported_pack, worker, assessor_headers):
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    signed = _sign_off(client, a["id"], assessor_headers).json()

    r = client.get(f"/verify/{signed['report_uid']}")  # no auth at all -- public
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "SIGNED"
    assert body["valid"] is True
    assert body["qp"] == "CON/Q0602 v4.0"
    assert body["recommendation"] == "RECOMMEND_CERTIFICATION"
    assert body["sha256"] == signed["pdf_sha256"]
    # Never worker identity, raw evidence, or the full score breakdown.
    for forbidden in ("worker_name", "worker_id", "criteria", "evidence", "nos_breakdown"):
        assert forbidden not in body


def test_public_verify_nonexistent_report_id_is_404(client):
    r = client.get("/verify/not-a-real-report-id")
    assert r.status_code == 404


def test_public_verify_detects_a_tampered_pdf_file(client, imported_pack, worker, assessor_headers, db_session):
    """The actual tamper-evidence proof: flip one byte of the STORED PDF
    file on disk (simulating an attacker with storage write access) and
    confirm /verify/{report_id} flips from valid to invalid. This is the
    P7 redesign's replacement for the old JSON-snapshot tamper test -- what
    is now signed is the PDF's own bytes, not a JSON document."""
    import server.app.routers.uploads as uploads_router
    from server.app import models

    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    signed = _sign_off(client, a["id"], assessor_headers).json()

    before = client.get(f"/verify/{signed['report_uid']}")
    assert before.json()["valid"] is True

    report = db_session.query(models.SignedReport).filter_by(assessment_id=a["id"]).one()
    original_bytes = uploads_router._storage.read(report.pdf_storage_key)
    tampered = bytearray(original_bytes)
    tampered[-10] ^= 0xFF  # flip one byte, deep inside the trailer, far from any padding
    uploads_router._storage.write(report.pdf_storage_key, bytes(tampered))

    after = client.get(f"/verify/{signed['report_uid']}")
    assert after.status_code == 200
    assert after.json()["valid"] is False

    # And the legacy per-assessment verify endpoint must agree.
    legacy = client.get(f"/reports/{a['id']}/verify")
    assert legacy.json()["valid"] is False
