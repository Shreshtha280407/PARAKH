"""Tamper-evident signed reports -- P7 redesign: password-confirmed
sign-off, PDF-bytes-first Ed25519 signing, immutable stored artifact,
public /verify/{report_id}. See server/app/report_signing.py,
routers/reports.py, routers/verify.py, docs/gates/P7.md sections 4-5.
"""
import threading
import time

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from server.app import models, schemas
from server.app.routers import scoring

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


def test_sign_off_repeat_call_still_validates_the_password(client, imported_pack, worker, assessor_headers):
    """A report already existing must never become a way to skip the
    password check -- every sign-off call proves the password, including
    a retry against an assessment that's already signed off."""
    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    first = _sign_off(client, a["id"], assessor_headers)
    assert first.status_code == 201

    wrong = _sign_off(client, a["id"], assessor_headers, password="definitely not the password")
    assert wrong.status_code == 401, wrong.text

    correct = _sign_off(client, a["id"], assessor_headers)
    assert correct.status_code == 201
    assert correct.json() == first.json()  # still the exact same stored artifact


def test_put_score_blocks_on_and_then_loses_to_a_concurrent_sign_off(client, imported_pack, worker, assessor_headers, db_session):
    """put_score() and sign_off() must lock the SAME assessment row (see
    the comment at the top of put_score) -- otherwise a score save that
    starts just before a sign-off can land just after it, mutating an
    assessment a report was already produced from. Requires real
    PostgreSQL (row-level locking); fails loudly rather than skipping
    otherwise, like test_jobs.py::test_concurrent_claims_never_double_process."""
    if db_session.bind.dialect.name != "postgresql":
        pytest.fail(
            "this test requires TEST_DATABASE_URL to point at a real PostgreSQL database -- "
            "SQLite has no row-level locking, so FOR UPDATE blocking cannot be demonstrated "
            "against it. See server/README.md for how to run against the dockerized Postgres."
        )

    a = _recommended_assessment(client, imported_pack, worker, assessor_headers)
    pc_full_id = client.get(f"/assessments/{a['id']}/review", headers=assessor_headers).json()[0]["pc_full_id"]

    # NOT str(db_session.bind.url) -- that redacts the password. Two
    # independent connections, like the real sign-off request and the
    # real score-save request each getting their own DB connection.
    url = db_session.bind.url.render_as_string(hide_password=False)
    SessionLock = sessionmaker(bind=create_engine(url))
    SessionScore = sessionmaker(bind=create_engine(url))

    lock_acquired = threading.Event()
    score_attempting = threading.Event()
    release_lock = threading.Event()
    result: dict = {}

    def _hold_assessment_lock_like_sign_off():
        s = SessionLock()
        try:
            s.execute(select(models.Assessment).where(models.Assessment.id == a["id"]).with_for_update())
            lock_acquired.set()
            release_lock.wait(timeout=5)
            assessment = s.get(models.Assessment, a["id"])
            assessment.status = "recommended"  # exactly what sign_off() does before releasing
            s.commit()
        finally:
            s.close()

    def _attempt_concurrent_score_save():
        assert lock_acquired.wait(timeout=5)
        s = SessionScore()
        try:
            user = s.query(models.User).filter_by(email="assessor@test.local").one()
            body = schemas.CriterionScoreIn(
                pc_full_id=pc_full_id, score_level=2, evidence_status="DEMONSTRATED", expected_version=1,
            )
            started = time.monotonic()
            result["backend_pid"] = s.connection().exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
            score_attempting.set()
            try:
                scoring.put_score(a["id"], body, s, user)
                result["outcome"] = "unexpectedly_succeeded"
            except HTTPException as exc:
                result["outcome"] = "rejected"
                result["status_code"] = exc.status_code
            result["elapsed"] = time.monotonic() - started
        finally:
            s.close()

    t_lock = threading.Thread(target=_hold_assessment_lock_like_sign_off)
    t_score = threading.Thread(target=_attempt_concurrent_score_save)
    t_lock.start()
    t_score.start()
    try:
        assert score_attempting.wait(timeout=5), "score thread did not reach its database call"
        # Wait for actual PostgreSQL lock contention, not connection-startup timing.
        # The previous sleep started before opening the score connection; under load
        # 80ms of that 300ms window could be spent connecting, leaving only 220ms of
        # real blocking and failing the unchanged >=250ms assertion below.
        deadline = time.monotonic() + 3
        with SessionScore.kw["bind"].connect() as observer:
            while time.monotonic() < deadline:
                waiting = observer.exec_driver_sql(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s",
                    (result["backend_pid"],),
                ).scalar_one_or_none()
                observer.rollback()  # refresh pg_stat_activity's transaction snapshot
                if waiting == "Lock":
                    break
                time.sleep(0.01)
            else:
                pytest.fail("score save never blocked on the assessment lock")
        time.sleep(0.3)  # hold the observed lock for the original minimum duration
    finally:
        release_lock.set()
        t_lock.join(timeout=5)
        t_score.join(timeout=5)

    # Proves put_score genuinely WAITED on the lock (not a lucky race) and,
    # once unblocked, correctly saw the post-sign-off status and rejected --
    # never silently wrote a score the signed report can no longer reflect.
    assert result["elapsed"] >= 0.25, "put_score did not actually block on the assessment lock"
    assert result["outcome"] == "rejected"
    assert result["status_code"] == 409


def test_render_pdf_never_truncates_hashes_reasons_or_remarks():
    """Direct unit test of _render_pdf (pure function, no DB/HTTP needed --
    same spirit as test_outcome.py) proving every piece of evidentiary
    text survives in full: a real 64-char sha256 (never shortened -- that
    IS the integrity record a verifier checks a file against), and
    override reasons / PC remarks / reassessment reasons long enough that
    the old fixed-length slices would have cut them off. pageCompression=0
    keeps the rendered content plain-text greppable, so a literal
    substring check on the raw bytes is a faithful proof, not a reportlab
    internals assumption."""
    from server.app.routers.reports import REPORT_DISCLAIMER, _render_pdf

    full_hash = "ab" * 32
    assert len(full_hash) == 64
    # Each string pads PAST the old fixed-length slice before a UNIQUE
    # marker word that appears nowhere earlier in the string -- repeating
    # the same filler phrase wouldn't prove anything (the old truncated
    # slice would still contain copies of every repeated word); only a
    # tail-only marker proves the full text, not a prefix, made it through.
    long_override_reason = "Filler padding word. " * 8 + "OVERRIDEUNIQUETAILMARKER"  # marker starts at char 168, past [:140]
    long_remark = "Remark padding word. " * 7 + "REMARKUNIQUETAILMARKER"  # marker starts at char 147, past [:110]
    long_reassessment_reason = "Reassessment padding word. " * 6 + "REASSESSMENTUNIQUETAILMARKER"  # marker starts at char 162, past [:100]
    assert len(long_override_reason) - len("OVERRIDEUNIQUETAILMARKER") > 140
    assert len(long_remark) - len("REMARKUNIQUETAILMARKER") > 110
    assert len(long_reassessment_reason) - len("REASSESSMENTUNIQUETAILMARKER") > 100

    data = {
        "report_uid": "rpt-1", "assessment_id": 1, "revision_number": 1,
        "verify_url": "http://localhost:5173/#/verify/rpt-1",
        "worker_name": "Test Worker", "qp_code": "CON/Q0602", "qp_name": "Assistant Electrician",
        "qp_version": "1.0", "rubric_version": "1.0",
        "declaration": {"recorded": False, "match_result": None, "coverage_percent": None, "gap_task_codes": None, "match_reasons": None},
        "nos_breakdown": [{
            "nos_code": "CON/N0602", "nos_title": "Title", "marks_awarded": "10.00", "marks_possible": "10.00",
            "percent": 100.0, "meets_threshold": True, "critical_violation": False,
            "has_insufficient_evidence": False, "competent": True,
        }],
        "criteria_by_task": {"T1": [{
            "pc_full_id": "CON/N0602.PC1", "nos_code": "CON/N0602", "critical": False, "max_marks": "10.00",
            "score_level": 3, "evidence_status": "DEMONSTRATED", "assessor_comment": long_remark,
            "marks_awarded": "10.00", "revision_number": 1,
        }]},
        "computed_recommendation": "RECOMMEND_CERTIFICATION", "final_recommendation": "NOT_YET_COMPETENT",
        "override_reason": long_override_reason, "assessor_remarks": None,
        "evidence": [{
            "task_code": "T1", "kind": "photo", "sha256": full_hash, "declared_size_bytes": 12345,
            "device_captured_at": None, "received_at": "2026-01-01T00:00:00+00:00",
        }],
        "revision_history": [],
        "reassessment_history": [{
            "task_codes": ["T1"], "reason": long_reassessment_reason,
            "capture_instructions": "x", "requested_at": "2026-01-01T00:00:00+00:00", "status": "pending",
        }],
        "assessor_name": "Test Assessor", "minimum_aggregate_passing_percent": 50,
        "disclaimer": REPORT_DISCLAIMER,
    }

    pdf_bytes = _render_pdf(data)

    assert full_hash.encode() in pdf_bytes
    assert b"OVERRIDEUNIQUETAILMARKER" in pdf_bytes
    assert b"REMARKUNIQUETAILMARKER" in pdf_bytes
    assert b"REASSESSMENTUNIQUETAILMARKER" in pdf_bytes


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
