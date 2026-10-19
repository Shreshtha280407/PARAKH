"""Real database contracts; email delivery is mocked only at the transport boundary."""
import datetime
import json
import secrets

import pytest

from server.app import models
from server.app.config import settings
from server.app.routers import reviewer


def enrollment(**changes):
    return {"device_worker_id": "KP-" + secrets.token_hex(16), "enrollment_secret": secrets.token_hex(32),
            "client_assessment_id": secrets.token_hex(16), "full_name": "Asha Kumar", "phone": "+919876543210",
            "public_name_consent": False, **changes}


def submitted(client, **changes):
    body = enrollment(**changes)
    response = client.post("/workers/enroll", json=body)
    assert response.status_code == 200, response.text
    assessment = response.json()
    assert client.post(f"/assessments/{assessment['id']}/submit", headers={"X-Worker-Token": assessment["worker_token"]}).status_code == 200
    return assessment, body


@pytest.fixture
def mailbox(monkeypatch):
    monkeypatch.setattr(settings, "reviewer_smtp_host", "smtp.test.invalid")
    monkeypatch.setattr(settings, "reviewer_email_from", "parakh@test.invalid")
    monkeypatch.setattr(settings, "reviewer_allowed_emails", "reviewer@test.invalid")
    codes = []
    monkeypatch.setattr(reviewer, "send_code", lambda email, code, assessment_id, action: codes.append(code))
    return codes


def authorize(client, mailbox, assessment_id, action="review"):
    response = client.post("/reviewer/challenges", json={"assessment_id": assessment_id,
        "name": "Reviewer Name", "email": "reviewer@test.invalid", "action": action})
    assert response.status_code == 200, response.text
    challenge_id = response.json()["challenge_id"]
    verified = client.post("/reviewer/verify", json={"challenge_id": challenge_id, "code": mailbox[-1]})
    assert verified.status_code == 200, verified.text
    assert verified.json()["email_verified"] is True
    assert verified.json()["name_verified"] is False
    return {"X-Reviewer-CSRF": client.cookies.get(reviewer.CSRF_COOKIE)}


def test_identity_persistence_retry_and_phone_privacy(client, imported_pack, db_session):
    body = enrollment(public_name_consent=True)
    first = client.post("/workers/enroll", json=body)
    retry = client.post("/workers/enroll", json=body)
    assert first.status_code == retry.status_code == 200
    assert first.json() == retry.json()
    row = db_session.get(models.User, first.json()["worker_id"])
    assert row.display_name == "Asha Kumar" and row.candidate_phone == body["phone"]
    assert row.phone is None and row.password_hash is None
    assert row.enrollment_secret_hash != body["enrollment_secret"]
    assert body["phone"] not in first.text and body["enrollment_secret"] not in first.text
    client.post(f"/assessments/{first.json()['id']}/submit", headers={"X-Worker-Token": first.json()["worker_token"]})
    listing = client.get("/public/assessments")
    assert listing.json()[0]["candidate_display_name"] == "Asha Kumar"
    assert body["phone"] not in listing.text and "token" not in listing.text
    assert "storage_key" not in listing.text and "pin" not in listing.text


@pytest.mark.parametrize("phone", ["12345", "+911234567890", "9876543210", "+91987654321a"])
def test_phone_validation(client, imported_pack, phone):
    assert client.post("/workers/enroll", json=enrollment(phone=phone)).status_code == 422


def test_enrollment_rejects_pin_and_identity_takeover(client, imported_pack):
    body = enrollment()
    first = client.post("/workers/enroll", json=body).json()
    invalid = client.post("/workers/enroll", json={**body, "pin": "1234"})
    assert invalid.status_code == 422 and "1234" not in invalid.text
    assert body["phone"] not in invalid.text and body["enrollment_secret"] not in invalid.text
    assert client.post("/workers/enroll", json={**body, "enrollment_secret": secrets.token_hex(32)}).status_code == 409
    assert client.post("/workers/enroll", json={**body, "full_name": "Someone Else"}).status_code == 409
    assert client.post("/assessments", json={"worker_id": first["worker_id"], "pack_id": imported_pack.id}).status_code == 403


def test_legacy_test_records_hidden_and_new_records_pseudonymous(client, imported_pack, worker):
    old = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    client.post(f"/assessments/{old['id']}/submit", headers={"X-Worker-Token": old["worker_token"]})
    assert client.get("/public/assessments").json() == []
    new, _ = submitted(client)
    rows = client.get("/public/assessments").json()
    assert len(rows) == 1 and rows[0]["id"] == new["id"]
    assert rows[0]["candidate_display_name"] == f"Candidate #{new['id']}"
    assert client.get(f"/public/assessments/{old['id']}").status_code == 404
    assert client.post("/public/assessments").status_code == 405


def test_private_routes_and_anonymous_scoring_stay_closed(client, imported_pack):
    a, _ = submitted(client)
    for path in ("", "/review", "/evidence/1/content", "/report"):
        assert client.get(f"/assessments/{a['id']}{path}").status_code == 401
        assert client.get(f"/reviewer/assessments/{a['id']}{path}").status_code == 401
    for prefix in ("", "/reviewer"):
        response = client.put(f"{prefix}/assessments/{a['id']}/review", json={
            "pc_full_id": "CON/N0602.PC1", "score_level": 3, "evidence_status": "DEMONSTRATED", "expected_version": 0})
        assert response.status_code == 401


def test_email_unavailable_and_unlisted_reviewer_fail_closed(client, imported_pack, monkeypatch, mailbox):
    a, _ = submitted(client)
    body = {"assessment_id": a["id"], "name": "Reviewer", "email": "stranger@test.invalid", "action": "sign_off"}
    assert client.post("/reviewer/challenges", json=body).status_code == 403
    monkeypatch.setattr(settings, "reviewer_smtp_host", None)
    assert client.post("/reviewer/challenges", json=body).status_code == 503


def test_code_attempt_limit_replay_and_no_permanent_account(client, imported_pack, mailbox, db_session):
    a, _ = submitted(client)
    challenge = client.post("/reviewer/challenges", json={"assessment_id": a["id"], "name": "Reviewer", "email": "reviewer@test.invalid", "action": "review"}).json()
    wrong = "000001" if mailbox[-1] != "000001" else "000002"
    for _ in range(5):
        assert client.post("/reviewer/verify", json={**challenge, "code": wrong}).status_code == 401
    assert client.post("/reviewer/verify", json={**challenge, "code": mailbox[-1]}).status_code == 401
    headers = authorize(client, mailbox, a["id"])
    row = db_session.query(models.ReviewerChallenge).order_by(models.ReviewerChallenge.expires_at.desc()).first()
    assert client.post("/reviewer/verify", json={"challenge_id": row.id, "code": mailbox[-1]}).status_code == 401
    assert db_session.query(models.User).count() == 1
    assert client.post(f"/reviewer/assessments/{a['id']}/start-review", headers=headers).status_code == 200


def test_scopes_csrf_expiry_and_live_permission(client, imported_pack, mailbox, db_session, monkeypatch):
    a, _ = submitted(client)
    b, _ = submitted(client)
    headers = authorize(client, mailbox, a["id"])
    assert client.get(f"/reviewer/assessments/{b['id']}").status_code == 403
    assert client.post(f"/reviewer/assessments/{a['id']}/start-review").status_code == 403
    assert client.post(f"/reviewer/assessments/{a['id']}/reject", json={"reason": "unclear", "confirmed": True}, headers=headers).status_code == 403
    monkeypatch.setattr(settings, "reviewer_allowed_emails", "")
    assert client.get(f"/reviewer/assessments/{a['id']}").status_code == 403
    monkeypatch.setattr(settings, "reviewer_allowed_emails", "reviewer@test.invalid")
    session = db_session.query(models.ReviewerSession).one()
    session.expires_at = models.utcnow() - datetime.timedelta(seconds=1)
    db_session.commit()
    assert client.get(f"/reviewer/assessments/{a['id']}").status_code == 401


def test_legacy_email_rejection_cannot_bypass_password_finalization(client, imported_pack, mailbox, db_session):
    a, _ = submitted(client)
    review_headers = authorize(client, mailbox, a["id"])
    client.post(f"/reviewer/assessments/{a['id']}/start-review", headers=review_headers)
    headers = authorize(client, mailbox, a["id"], "reject")
    response = client.post(f"/reviewer/assessments/{a['id']}/reject", json={"reason": "Safety not demonstrated", "confirmed": True}, headers=headers)
    assert response.status_code == 403 and 'password-based' in response.text
    assert db_session.query(models.SignedReport).count() == 0
    assert db_session.query(models.AuditLog).filter_by(action='rejected').count() == 0


def test_targeted_reassessment_uses_existing_revision_history(client, imported_pack, mailbox, db_session):
    a, _ = submitted(client)
    headers = authorize(client, mailbox, a["id"], "reassessment")
    response = client.post(f"/reviewer/assessments/{a['id']}/reassessment-requests", headers=headers,
        json={"task_codes": ["T4"], "reason": "Board not visible", "capture_instructions": "Show entire board", "confirmed": True})
    assert response.status_code == 201, response.text
    assert response.json()["requested_by_id"] == 0  # Older Android clients require an integer.
    updates = client.get(f"/assessments/{a['id']}/worker-updates", headers={"X-Worker-Token": a["worker_token"]})
    assert updates.status_code == 200
    assert updates.json()["pending_reassessment_request"]["requested_by_id"] == 0
    request = db_session.query(models.ReassessmentRequest).one()
    assert request.task_codes == ["T4"] and request.requested_by_id is None
    assert request.reviewer_identity["email_verified"] is True
    assert db_session.get(models.Assessment, a["id"]).revision_number == 2
    assert db_session.query(models.AssessmentRevision).count() == 2


def test_human_scoring_signed_identity_and_public_verification(client, imported_pack, mailbox, db_session):
    a, _ = submitted(client)
    headers = authorize(client, mailbox, a["id"])
    assert client.post(f"/reviewer/assessments/{a['id']}/start-review", headers=headers).status_code == 200
    items = client.get(f"/reviewer/assessments/{a['id']}/review").json()
    for item in items:
        response = client.put(f"/reviewer/assessments/{a['id']}/review", headers=headers,
            json={"pc_full_id": item["pc_full_id"], "score_level": 3, "evidence_status": "DEMONSTRATED", "expected_version": 0})
        assert response.status_code == 200, response.text
    headers = authorize(client, mailbox, a["id"], "sign_off")
    response = client.post(f"/reviewer/assessments/{a['id']}/sign-off", headers=headers,
        json={"final_recommendation": "RECOMMEND_CERTIFICATION", "confirmed": True})
    assert response.status_code == 403 and 'password-based' in response.text
    from server.tests.test_reviewer_accounts import register, PASSWORD
    headers = register(client)
    response = client.post(f"/reviewer/assessments/{a['id']}/sign-off", headers=headers,
        json={"final_recommendation":"RECOMMEND_CERTIFICATION", "confirmed":True, "password":PASSWORD})
    assert response.status_code == 201, response.text
    signed = db_session.query(models.SignedReport).one()
    assert signed.signed_by_id is None and signed.reviewer_identity["email_verified"] is False
    assert json.loads(signed.canonical_json)["reviewer_identity"]["name_verified"] is False
    assert client.get(f"/verify/{signed.report_uid}").json()["valid"] is True
    listing = client.get("/public/assessments").json()[0]
    assert listing['report_available'] is False and listing['outcome'] is None
    assert client.put(f"/assessments/{a['id']}/public-outcome-consent", headers={'X-Worker-Token':a['worker_token']},
        json={'consent':True,'consent_version':'public-outcome-v1'}).status_code == 200
    listing = client.get("/public/assessments").json()[0]
    assert listing["report_available"] and listing["report_id"] == signed.report_uid
    assert "Reviewer Name" not in client.get("/public/assessments").text


def test_signing_incomplete_scores_rejected(client, imported_pack):
    a, _ = submitted(client)
    from server.tests.test_reviewer_accounts import register, PASSWORD
    headers = register(client)
    assert client.post(f"/reviewer/assessments/{a['id']}/start-review", headers=headers).status_code == 200
    assert client.post(f"/reviewer/assessments/{a['id']}/sign-off", headers=headers,
        json={"final_recommendation": "RECOMMEND_CERTIFICATION", "confirmed": True, "password":PASSWORD}).status_code == 409


def test_abuse_limit_and_retry_at_capacity(client, imported_pack, monkeypatch):
    body = enrollment()
    first = client.post("/workers/enroll", json=body)
    monkeypatch.setattr(settings, "public_enrollment_max_assessments", 1)
    assert client.post("/workers/enroll", json=body).json() == first.json()
    assert client.post("/workers/enroll", json=enrollment()).status_code == 503
    monkeypatch.setattr(settings, "public_enrollment_max_assessments", 200)
    for _ in range(20):
        result = client.post("/workers/enroll", json=body)
    assert result.status_code == 429


def test_targeted_reassessment_waits_for_signing_lock_and_cannot_reopen_final_decision(client, imported_pack, db_session):
    import threading
    import time
    from fastapi import HTTPException
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from server.app import schemas
    from server.app.reviewer_identity import ReviewerActor
    from server.app.routers.reassessment import create_reassessment_request

    assert db_session.bind.dialect.name == "postgresql", "race proof requires PostgreSQL"
    a, _ = submitted(client)
    engine = create_engine(db_session.bind.url)
    session_factory = sessionmaker(bind=engine)
    result = {}
    ready = threading.Event()
    done = threading.Event()
    with session_factory() as signing:
        assessment = signing.execute(select(models.Assessment).where(models.Assessment.id == a["id"]).with_for_update()).scalar_one()

        def request():
            with session_factory() as db:
                result["pid"] = db.connection().exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
                ready.set()
                try:
                    create_reassessment_request(a["id"], schemas.ReassessmentRequestIn(task_codes=["T4"], reason="unclear", capture_instructions="retake"),
                                                db, ReviewerActor("Reviewer", "reviewer@test.invalid", "test-session"))
                    result["status"] = 201
                except HTTPException as error:
                    result["status"] = error.status_code
                finally:
                    done.set()

        thread = threading.Thread(target=request)
        thread.start()
        try:
            assert ready.wait(5)
            deadline = time.monotonic() + 5
            with engine.connect() as observer:
                while time.monotonic() < deadline:
                    state = observer.exec_driver_sql("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", (result["pid"],)).scalar_one_or_none()
                    observer.rollback()
                    if state == "Lock":
                        break
                    time.sleep(0.01)
                else:
                    pytest.fail("reassessment did not block on the sign-off assessment lock")
            assert not done.is_set()
            assessment.status = "recommended"  # Signing's terminal transition, while retaining its lock.
            signing.commit()
        finally:
            signing.rollback()
            thread.join(10)
    assert result["status"] == 409
    assert not thread.is_alive()
    db_session.expire_all()
    assert db_session.query(models.ReassessmentRequest).count() == 0
    assert db_session.get(models.Assessment, a["id"]).revision_number == 1
    engine.dispose()
