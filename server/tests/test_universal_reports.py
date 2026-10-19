"""Real API/PDF/Ed25519 regressions; concurrency requires disposable PostgreSQL."""
import concurrent.futures
import hashlib
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from server.app import models, report_signing
from server.app.db import get_db
from server.app.main import app
from server.app.report_outcomes import decision_for
from server.app.routers import reports, uploads
from server.tests.test_open_access import submitted
from server.tests.test_reviewer_accounts import register, PASSWORD
from server.tests.test_reports import _score_all_pcs, ASSESSOR_PASSWORD


def candidate_review(client, assessor_headers, *, name_consent=False):
    assessment, _ = submitted(client, public_name_consent=name_consent)
    assert client.post(f"/assessments/{assessment['id']}/start-review", headers=assessor_headers).status_code == 200
    return assessment


def sign(client, assessment_id, headers, outcome="RECOMMEND_CERTIFICATION"):
    return client.post(f"/assessments/{assessment_id}/sign-off", headers=headers, json={
        "password": ASSESSOR_PASSWORD, "final_recommendation": outcome,
        "override_reason": "Explicit human final judgement for this regression fixture",
    })


def reject(client, assessment_id, headers, password=PASSWORD):
    return client.post(f"/reviewer/assessments/{assessment_id}/reject", headers=headers,
        json={"password": password, "reason": "Safety criteria not demonstrated; do not recommend", "confirmed": True})


@pytest.mark.parametrize("outcome,level", [("RECOMMEND_CERTIFICATION", 3), ("NOT_YET_COMPETENT", 0), ("PARTIALLY_COMPETENT", 2)])
def test_final_signatures_bind_real_outcome_pdf_and_state(client, imported_pack, assessor_headers, db_session, outcome, level):
    a = candidate_review(client, assessor_headers)
    _score_all_pcs(client, a['id'], assessor_headers, level=level)
    response = sign(client, a['id'], assessor_headers, outcome)
    assert response.status_code == 201, response.text
    report = response.json()
    row = db_session.get(models.Assessment, a['id'])
    assert row.status == row.decision == decision_for(outcome)
    pdf = client.get(f"/assessments/{a['id']}/report?format=pdf", headers=assessor_headers)
    assert pdf.status_code == 200
    assert hashlib.sha256(pdf.content).hexdigest() == report['pdf_sha256']
    assert report_signing.verify_pdf(pdf.content, report['pdf_sha256'], report['signature'], report['key_id'])
    assert f"Final \\(assessor\\): {outcome}".encode() in pdf.content
    assert report['report_uid'].encode() in pdf.content
    assert report_signing.bound_metadata(pdf.content)['final_recommendation'] == outcome
    public = client.get('/verify/'+report['report_uid']).json()
    assert public['valid'] is True and public['recommendation'] == outcome and public['metadata_bound'] is True
    private = client.get(f"/assessments/{a['id']}", headers=assessor_headers).json()
    assert private['signed_report']['report_uid'] == report['report_uid']
    assert private['status'] == private['decision'] == row.decision


def test_rejection_issues_report_and_retry_is_idempotent_and_password_confirmed(client, imported_pack, assessor_headers, db_session):
    a = candidate_review(client, assessor_headers)
    headers = register(client)
    assert reject(client, a['id'], headers, 'incorrect-password').status_code == 403
    assert reject(client, a['id'], {}).status_code == 403  # CSRF remains mandatory
    first = reject(client, a['id'], headers)
    assert first.status_code == 200, first.text
    report = first.json()['signed_report']
    assert first.json()['status'] == first.json()['decision'] == 'not_recommended'
    assert report['final_recommendation'] == 'NOT_YET_COMPETENT'
    assert reject(client, a['id'], headers).json()['signed_report'] == report
    assert reject(client, a['id'], headers, 'incorrect-password').status_code == 403
    assert db_session.query(models.SignedReport).count() == 1
    assert db_session.query(models.AuditLog).filter_by(action='rejected').count() == 1
    assert db_session.query(models.AuditLog).filter_by(action='signed_off').count() == 1
    snapshot = json.loads(db_session.query(models.SignedReport).one().canonical_json)
    assert snapshot['finalization_action'] == 'rejected'
    assert snapshot['computed_recommendation'] == 'INSUFFICIENT_EVIDENCE'
    assert snapshot['assessor_remarks'] == 'Safety criteria not demonstrated; do not recommend'
    assert all(pc['marks_awarded'] is None for pcs in snapshot['criteria_by_task'].values() for pc in pcs)
    assert client.get('/verify/'+report['report_uid']).json()['valid'] is True
    # An incompatible subsequent decision cannot quietly return success.
    assert sign(client, a['id'], assessor_headers).status_code == 409


def test_publication_is_candidate_controlled_separate_from_name_consent(client, imported_pack, assessor_headers, db_session):
    positive = candidate_review(client, assessor_headers)
    _score_all_pcs(client, positive['id'], assessor_headers)
    positive_report = sign(client, positive['id'], assessor_headers).json()
    negative = candidate_review(client, assessor_headers, name_consent=True)
    headers = register(client)
    negative_report = reject(client, negative['id'], headers).json()['signed_report']
    assert client.get('/public/reports').json() == []
    for a, report in [(positive, positive_report), (negative, negative_report)]:
        summary = client.get(f"/public/assessments/{a['id']}").json()
        assert summary['status'] == 'finalized' and summary['outcome'] is None
        assert summary['report_id'] is None and summary['report_available'] is False
        assert client.get('/verify/'+report['report_uid']).json()['valid'] is True
        endpoint = f"/assessments/{a['id']}/public-outcome-consent"
        body = {'consent': True, 'consent_version': 'public-outcome-v1'}
        assert client.put(endpoint, json=body, headers=assessor_headers).status_code == 401
        assert client.put(endpoint, json=body, headers={'X-Worker-Token':'invalid'}).status_code == 401
        response = client.put(endpoint, json=body, headers={'X-Worker-Token':a['worker_token']})
        assert response.status_code == 200 and response.json()['consent'] is True
    public = client.get('/public/reports')
    assert public.headers['cache-control'] == 'no-store'
    rows = {item['id']: item for item in public.json()}
    assert rows[positive['id']]['candidate_display_name'] == f"Candidate #{positive['id']}"
    assert rows[positive['id']]['status'] == 'recommended'
    assert rows[negative['id']]['candidate_display_name'] == 'Asha Kumar'
    assert rows[negative['id']]['status'] == 'not_recommended'
    assert rows[negative['id']]['outcome'] == 'NOT_YET_COMPETENT'
    assert all(item['report_id'] and item['report_issued_at'] for item in rows.values())
    for forbidden in ('phone', 'worker_token', 'enrollment_secret', 'pdf_storage_key', 'scores', 'evidence', 'signature'):
        assert forbidden not in public.text
    assert '9876543210' not in public.text
    private = client.get('/reviewer/queue')
    assert private.headers['cache-control'] == 'private, no-store'
    assert any(row['report_id'] == negative_report['report_uid'] for row in private.json())
    revoked = client.put(f"/assessments/{negative['id']}/public-outcome-consent", headers={'X-Worker-Token':negative['worker_token']},
        json={'consent': False, 'consent_version': 'public-outcome-v1'})
    assert revoked.status_code == 200
    assert [row['id'] for row in client.get('/public/reports').json()] == [positive['id']]
    assert client.get('/verify/'+negative_report['report_uid']).json()['valid'] is True
    client.cookies.clear()
    assert client.get('/reviewer/queue').status_code == 401
    assert client.get(f"/reviewer/assessments/{negative['id']}/report?format=pdf").status_code == 401
    assert client.get(f"/assessments/{negative['id']}/report?format=pdf").status_code == 401


@pytest.mark.parametrize('failure', ['render', 'sign', 'storage', 'readback', 'commit'])
def test_failure_rolls_back_finalization_and_retry_can_succeed(client, imported_pack, assessor_headers, db_session, monkeypatch, failure):
    a = candidate_review(client, assessor_headers)
    headers = register(client)
    def unavailable(*args, **kwargs):
        raise OSError('private failure detail must not be returned')
    with monkeypatch.context() as patch:
        if failure == 'render': patch.setattr(reports, '_render_pdf', unavailable)
        elif failure == 'sign': patch.setattr(report_signing, 'sign_pdf', unavailable)
        elif failure == 'storage': patch.setattr(uploads._storage, 'write_once', unavailable)
        elif failure == 'readback': patch.setattr(uploads._storage, 'read', lambda key: b'tampered during storage')
        else:
            original_commit = db_session.commit
            def fail_final_commit():
                # The rate limiter commits its counters BEFORE business work.
                # Inject failure only after the actual report row was flushed.
                if any(isinstance(row, models.SignedReport) for row in db_session.identity_map.values()):
                    unavailable()
                return original_commit()
            patch.setattr(db_session, 'commit', fail_final_commit)
        response = reject(client, a['id'], headers)
    assert response.status_code == 503, response.text
    assert 'private failure detail' not in response.text
    db_session.expire_all()
    assessment = db_session.get(models.Assessment, a['id'])
    assert assessment.status == 'in_review' and assessment.decision is None
    assert db_session.query(models.SignedReport).count() == 0
    assert db_session.query(models.AuditLog).filter(models.AuditLog.action.in_(['signed_off','rejected'])).count() == 0
    retry = reject(client, a['id'], headers)
    assert retry.status_code == 200, retry.text
    assert client.get('/verify/'+retry.json()['signed_report']['report_uid']).json()['valid'] is True


@pytest.mark.parametrize('damage', ['pdf', 'signature', 'missing', 'outcome_metadata'])
def test_negative_report_tampering_is_not_authentic(client, imported_pack, assessor_headers, db_session, damage):
    a = candidate_review(client, assessor_headers)
    headers = register(client)
    assert reject(client, a['id'], headers).status_code == 200
    report = db_session.query(models.SignedReport).one()
    if damage == 'pdf':
        data = bytearray(uploads._storage.read(report.pdf_storage_key)); data[-10] ^= 1
        uploads._storage.write(report.pdf_storage_key, bytes(data))
    elif damage == 'missing': uploads._storage.delete(report.pdf_storage_key)
    elif damage == 'signature': report.signature = '00' * 64; db_session.commit()
    else: report.final_recommendation = 'RECOMMEND_CERTIFICATION'; db_session.commit()
    result = client.get('/verify/'+report.report_uid)
    assert result.status_code == 200 and result.json()['valid'] is False
    assert client.get(f"/reports/{a['id']}/verify").json()['valid'] is False
    assert client.get(f"/reviewer/assessments/{a['id']}/report?format=pdf").status_code == 409


def test_legacy_report_remains_byte_identical_and_verifiable(client, imported_pack, assessor_headers, db_session, monkeypatch):
    a = candidate_review(client, assessor_headers)
    _score_all_pcs(client, a['id'], assessor_headers)
    with monkeypatch.context() as patch:
        patch.setattr(report_signing, 'pdf_metadata', lambda data: 'Historical report')
        signed = sign(client, a['id'], assessor_headers).json()
    row = db_session.query(models.SignedReport).one()
    original = uploads._storage.read(row.pdf_storage_key)
    for _ in range(2):
        response = client.get('/verify/'+signed['report_uid'])
        assert response.json()['valid'] is True and response.json()['metadata_bound'] is False
        assert uploads._storage.read(row.pdf_storage_key) == original
    assert sign(client, a['id'], assessor_headers).json() == signed


def test_legacy_unsigned_rejection_is_not_backfilled(client, imported_pack, assessor_headers, db_session):
    a = candidate_review(client, assessor_headers)
    row = db_session.get(models.Assessment, a['id']); row.status = row.decision = 'not_recommended'; db_session.commit()
    headers = register(client)
    assert reject(client, a['id'], headers).status_code == 409
    assert db_session.query(models.SignedReport).count() == 0
    assert client.get('/public/reports').json() == []
    assert client.get(f"/reports/{a['id']}/verify").status_code == 404
    assert client.get('/verify/nonexistent-report-id').status_code == 404


@pytest.mark.parametrize('conflicting', [False, True])
def test_concurrent_finalizations_are_serialized_real_api(client, imported_pack, assessor_headers, db_session, monkeypatch, conflicting):
    assert db_session.bind.dialect.name == 'postgresql', 'requires disposable local PostgreSQL'
    a = candidate_review(client, assessor_headers)
    _score_all_pcs(client, a['id'], assessor_headers)
    sessions = sessionmaker(bind=db_session.bind, autoflush=False)
    def isolated_db():
        with sessions() as db:
            yield db
    monkeypatch.setitem(app.dependency_overrides, get_db, isolated_db)
    barrier = threading.Barrier(2)
    original_render = reports._render_pdf
    rendered = []
    def slow_render(snapshot):
        rendered.append(snapshot['report_uid']); time.sleep(.15)
        return original_render(snapshot)
    monkeypatch.setattr(reports, '_render_pdf', slow_render)
    def attempt(index):
        with TestClient(app) as connection:
            barrier.wait(timeout=10)
            if conflicting and index == 1:
                return connection.post(f"/assessments/{a['id']}/decision", headers=assessor_headers,
                    json={'decision':'not_recommended','password':ASSESSOR_PASSWORD,'notes':'Assessor declines recommendation'})
            return sign(connection, a['id'], assessor_headers)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, i) for i in range(2)]
        results = [future.result(timeout=30) for future in futures]
    codes = sorted(r.status_code for r in results)
    assert codes in ([200,409], [201,409]) if conflicting else codes == [201,201]
    db_session.expire_all()
    assert db_session.query(models.SignedReport).count() == len(rendered) == 1
    row = db_session.query(models.SignedReport).one()
    assessment = db_session.get(models.Assessment, a['id'])
    assert assessment.status == assessment.decision == decision_for(row.final_recommendation)
    assert client.get('/verify/'+row.report_uid).json()['valid'] is True


def test_insufficient_evidence_stays_in_reassessment_workflow(client, imported_pack, assessor_headers, db_session):
    a = candidate_review(client, assessor_headers)
    response = sign(client, a['id'], assessor_headers, 'INSUFFICIENT_EVIDENCE')
    assert response.status_code == 409 and 'reassessment' in response.text
    assert db_session.query(models.SignedReport).count() == 0
    assert client.post(f"/assessments/{a['id']}/reassessment-requests", headers=assessor_headers,
        json={'task_codes':['T1'],'reason':'Capture more evidence','capture_instructions':'Show the isolated tester check'}).status_code == 201
    assert sign(client, a['id'], assessor_headers).status_code == 409
    assert db_session.query(models.SignedReport).count() == 0


def test_reassessment_rechecks_cached_state_after_another_request_finalizes(client, imported_pack, assessor_headers, db_session, monkeypatch):
    """Password throttles can commit the earlier authorization row lock. A
    subsequent lock must refresh the identity-map object, not reuse its state.
    """
    a = candidate_review(client, assessor_headers)
    _score_all_pcs(client, a['id'], assessor_headers)
    cached = db_session.get(models.Assessment, a['id'])
    assert cached.status == 'in_review'
    sessions = sessionmaker(bind=db_session.bind, autoflush=False)
    def isolated_db():
        with sessions() as db:
            yield db
    original_override = app.dependency_overrides[get_db]
    with monkeypatch.context() as patch:
        patch.setitem(app.dependency_overrides, get_db, isolated_db)
        with TestClient(app) as other:
            assert sign(other, a['id'], assessor_headers).status_code == 201
    assert app.dependency_overrides[get_db] is original_override
    assert cached.status == 'in_review'  # Deliberately stale, as in the race.
    response = client.post(f"/assessments/{a['id']}/reassessment-requests", headers=assessor_headers,
        json={'task_codes':['T1'],'reason':'Retake the tester check','capture_instructions':'Show the zero reading'})
    assert response.status_code == 409, response.text
    assert db_session.query(models.ReassessmentRequest).count() == 0
    assert db_session.query(models.SignedReport).count() == 1
