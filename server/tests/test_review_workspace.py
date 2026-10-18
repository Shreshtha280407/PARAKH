"""Review payloads retain authorization and avoid per-row queries/read locks."""
from sqlalchemy import event

from server.app import models
from server.tests.test_open_access import submitted
from server.tests.test_reviewer_accounts import register


def test_workspace_metadata_matches_pack_and_history_requires_sign_in(client, imported_pack, db_session):
    assessment, _ = submitted(client)
    base = f"/reviewer/assessments/{assessment['id']}"
    for endpoint in ("workspace", "history"):
        assert client.get(f"{base}/{endpoint}").status_code == 401
    register(client)
    response = client.get(f"{base}/workspace")
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'private, no-store'
    result = response.json()
    assert result['assessment']['id'] == assessment['id']
    assert result['profile'] == client.get(f"{base}/competency-profile").json()
    assert result['sync'] == client.get(f"{base}/sync-status").json()
    assert result['review'] == client.get(f"{base}/review").json()
    assert result['review']
    tasks = {task.task_code: task for task in db_session.query(models.TaskTemplate).all()}
    pcs = {pc.full_id: pc for pc in db_session.query(models.PerformanceCriterion).all()}
    for item in result['review']:
        pc = pcs[item['pc_full_id']]
        assert item['criterion_text'] == pc.text
        assert item['task_code'] == pc.nos.task_code
        assert item['nos_title'] == pc.nos.title
        assert item['task_title'] == tasks[item['task_code']].title
        assert item['pc_full_id'] in tasks[item['task_code']].linked_pcs
    history = client.get(f"{base}/history")
    assert history.status_code == 200
    assert history.json()['revisions'] == client.get(f"{base}/revisions").json()
    assert history.json()['requests'] == client.get(f"{base}/reassessment-requests").json()
    assert history.json()['audit'] == client.get(f"{base}/audit-log").json()
    assert 'storage_key' not in response.text and 'worker_token' not in response.text


def test_account_workspace_reads_do_not_lock_assessment_rows(client, imported_pack, db_session):
    assessment, _ = submitted(client)
    register(client)
    statements = []
    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)
    event.listen(db_session.bind, 'before_cursor_execute', capture)
    try:
        for endpoint in ('workspace', 'history'):
            assert client.get(f"/reviewer/assessments/{assessment['id']}/{endpoint}").status_code == 200
    finally:
        event.remove(db_session.bind, 'before_cursor_execute', capture)
    assert not any('FOR UPDATE' in sql.upper() for sql in statements)
    assert db_session.get(models.Assessment, assessment['id']).status == 'submitted'


def test_public_queue_looks_up_reports_in_one_batch(client, imported_pack, db_session):
    ids = {submitted(client)[0]['id'] for _ in range(4)}
    statements = []
    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)
    event.listen(db_session.bind, 'before_cursor_execute', capture)
    try:
        response = client.get('/public/assessments')
    finally:
        event.remove(db_session.bind, 'before_cursor_execute', capture)
    assert response.status_code == 200
    assert {item['id'] for item in response.json()} == ids
    report_selects = [sql for sql in statements if 'SELECT' in sql.upper() and 'FROM signed_reports' in sql]
    assert len(report_selects) == 1


def test_sync_status_fetches_evidence_and_uploads_in_batches(client, imported_pack, worker, db_session):
    from server.tests.test_sync import _seal_and_sync_full_package
    assessment, token, *_ = _seal_and_sync_full_package(client, imported_pack, worker)
    statements = []
    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)
    event.listen(db_session.bind, 'before_cursor_execute', capture)
    try:
        response = client.get(f"/assessments/{assessment['id']}/sync-status", headers={'X-Worker-Token': token})
    finally:
        event.remove(db_session.bind, 'before_cursor_execute', capture)
    assert response.status_code == 200
    assert response.json()['all_items_verified'] is True
    assert len(response.json()['items']) == 2
    for table in ('evidence_items', 'upload_sessions', 'assessment_tasks'):
        assert len([sql for sql in statements if f'FROM {table}' in sql]) == 1
