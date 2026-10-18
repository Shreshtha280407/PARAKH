"""Password assessor registration, session authorization and per-action proof."""
import datetime
import json

import pytest

from server.app import models
from server.app.auth import verify_password
from server.app.routers import reviewer
from server.tests.test_open_access import submitted

PASSWORD = "test-only-assessor-passphrase"
ACCOUNT = {"name": "Test Assessor", "email": "Assessor@example.invalid", "phone": "9876543210",
           "password": PASSWORD, "password_acknowledged": True}


def register(client):
    response = client.post("/reviewer/accounts", json=ACCOUNT)
    assert response.status_code == 201, response.text
    return {"X-Reviewer-CSRF": client.cookies.get(reviewer.CSRF_COOKIE)}


def test_registration_requires_password_reminder_acknowledgement_and_hashes_secret(client, db_session):
    assert client.post("/reviewer/accounts", json={**ACCOUNT, "password_acknowledged": False}).status_code == 422
    assert client.post("/reviewer/accounts", json={**ACCOUNT, "password": "short"}).status_code == 422
    assert client.post("/reviewer/accounts", json={**ACCOUNT, "phone": "invalid"}).status_code == 422
    register(client)
    account = db_session.query(models.ReviewerAccount).one()
    assert account.email == ACCOUNT["email"].lower() and account.phone == ACCOUNT["phone"]
    assert account.password_hash != PASSWORD and verify_password(PASSWORD, account.password_hash)
    response = client.get("/reviewer/account")
    assert response.json()["email_verified"] is False
    assert PASSWORD not in response.text and "password_hash" not in response.text
    assert db_session.query(models.User).count() == 0
    assert client.post("/reviewer/accounts", json={**ACCOUNT, "email": ACCOUNT["email"].lower()}).status_code == 409


def test_login_logout_csrf_expiry_and_case_insensitive_email(client, db_session):
    headers = register(client)
    old_token = client.cookies.get(reviewer.COOKIE)
    assert client.post("/reviewer/logout").status_code == 403
    assert client.post("/reviewer/logout", headers=headers).status_code == 200
    client.cookies.set(reviewer.COOKIE, old_token, domain="testserver.local", path="/")
    assert client.get("/reviewer/account").status_code == 401
    for email in (ACCOUNT["email"], "missing@example.invalid"):
        response = client.post("/reviewer/sessions", json={"email":email,"password":"wrong-password"})
        assert response.status_code == 401 and response.json()["detail"] == "incorrect email or password"
    response = client.post("/reviewer/sessions", json={"email":" ASSESSOR@example.invalid ","password":PASSWORD})
    assert response.status_code == 200, response.text
    session = db_session.get(models.ReviewerAccountSession, reviewer.digest(client.cookies.get(reviewer.COOKIE)))
    session.expires_at = models.utcnow() - datetime.timedelta(seconds=1)
    db_session.commit()
    assert client.get("/reviewer/account").status_code == 401


def test_account_reviews_multiple_submissions_without_email_delivery(client, imported_pack):
    a, _ = submitted(client)
    b, _ = submitted(client)
    headers = register(client)
    for item in (a, b):
        assert client.get(f"/reviewer/assessments/{item['id']}").status_code == 200
        assert client.get(f"/assessments/{item['id']}").status_code == 401
        assert client.post(f"/reviewer/assessments/{item['id']}/start-review").status_code == 403
        assert client.post(f"/reviewer/assessments/{item['id']}/start-review", headers=headers).status_code == 200


@pytest.mark.parametrize("action,payload", [
    ("reject", {"reason":"Safety not demonstrated","confirmed":True}),
    ("reassessment-requests", {"task_codes":["T4"],"reason":"Retake board","capture_instructions":"Show full board","confirmed":True}),
    ("sign-off", {"final_recommendation":"RECOMMEND_CERTIFICATION","confirmed":True}),
])
def test_each_final_action_requires_password_on_server(client, imported_pack, db_session, action, payload):
    a, _ = submitted(client)
    headers = register(client)
    assert client.post(f"/reviewer/assessments/{a['id']}/start-review", headers=headers).status_code == 200
    for extra in ({}, {"password":"wrong-password"}):
        response = client.post(f"/reviewer/assessments/{a['id']}/{action}", headers=headers, json={**payload, **extra})
        assert response.status_code == 403, response.text
        assert PASSWORD not in response.text
    db_session.expire_all()
    assert db_session.get(models.Assessment, a["id"]).status == "in_review"
    assert db_session.query(models.SignedReport).count() == db_session.query(models.ReassessmentRequest).count() == 0


def test_correct_password_rejection_records_account_identity(client, imported_pack, db_session):
    a, _ = submitted(client)
    headers = register(client)
    client.post(f"/reviewer/assessments/{a['id']}/start-review", headers=headers)
    response = client.post(f"/reviewer/assessments/{a['id']}/reject", headers=headers,
        json={"reason":"Safety not demonstrated","confirmed":True,"password":PASSWORD})
    assert response.status_code == 200, response.text
    actor = db_session.query(models.AuditLog).filter_by(action="rejected").one().details["reviewer_identity"]
    assert actor["authorization"] == "password_account" and actor["email_verified"] is False
    assert actor["name"] == ACCOUNT["name"] and actor["account_id"]
    assert client.get(f"/reviewer/assessments/{a['id']}").status_code == 200


def test_correct_password_reassessment_reaches_worker(client, imported_pack):
    a, _ = submitted(client)
    headers = register(client)
    client.post(f"/reviewer/assessments/{a['id']}/start-review", headers=headers)
    response = client.post(f"/reviewer/assessments/{a['id']}/reassessment-requests", headers=headers,
        json={"task_codes":["T4"],"reason":"Retake board","capture_instructions":"Show full board","confirmed":True,"password":PASSWORD})
    assert response.status_code == 201, response.text
    updates = client.get(f"/assessments/{a['id']}/worker-updates", headers={"X-Worker-Token":a["worker_token"]}).json()
    assert updates["pending_reassessment_request"]["task_codes"] == ["T4"]


def test_password_signed_report_is_verifiable_and_retry_also_requires_password(client, imported_pack, db_session):
    a, _ = submitted(client)
    headers = register(client)
    client.post(f"/reviewer/assessments/{a['id']}/start-review", headers=headers)
    for item in client.get(f"/reviewer/assessments/{a['id']}/review").json():
        result = client.put(f"/reviewer/assessments/{a['id']}/review", headers=headers,
            json={"pc_full_id":item["pc_full_id"],"score_level":3,"evidence_status":"DEMONSTRATED","expected_version":0})
        assert result.status_code == 200
    payload = {"final_recommendation":"RECOMMEND_CERTIFICATION","confirmed":True,"password":PASSWORD}
    response = client.post(f"/reviewer/assessments/{a['id']}/sign-off", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    report = db_session.query(models.SignedReport).one()
    assert json.loads(report.canonical_json)["reviewer_identity"]["authorization"] == "password_account"
    assert client.get(f"/verify/{report.report_uid}").json()["valid"] is True
    assert client.post(f"/reviewer/assessments/{a['id']}/sign-off", headers=headers,
        json={**payload,"password":"wrong-password"}).status_code == 403
    assert client.post(f"/reviewer/assessments/{a['id']}/sign-off", headers=headers, json=payload).status_code == 201
