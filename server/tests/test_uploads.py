"""Resumable upload protocol tests. See server/app/routers/uploads.py's
module docstring for the ordered-sequential-chunks protocol this exercises.
"""
import hashlib
import threading

import pytest
from fastapi import HTTPException

WT_HEADER = "X-Worker-Token"


def _open_session(client, token, assessment_id, task_code="T2", size=10, mime="video/mp4", kind="video"):
    return client.post(
        "/uploads",
        json={"assessment_id": assessment_id, "task_code": task_code, "kind": kind, "mime": mime, "claimed_size_bytes": size},
        headers={WT_HEADER: token},
    )


def _new_assessment(client, imported_pack, worker):
    return client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()


def _upload_all_chunks(client, token, session_id, data: bytes, chunk_size: int = 1_000_000):
    """Split data into <= upload_chunk_max_bytes pieces and PUT them in
    order, asserting every single chunk is actually accepted (200) --
    silently ignoring a chunk's response status previously masked a real
    bug: a too-large single "chunk" was rejected (413) while the test kept
    going as if it had succeeded."""
    for i in range(0, len(data), chunk_size):
        idx = i // chunk_size
        chunk = data[i:i + chunk_size]
        r = client.put(f"/uploads/{session_id}/chunks/{idx}", content=chunk, headers={WT_HEADER: token})
        assert r.status_code == 200, f"chunk {idx} rejected: {r.status_code} {r.text}"


def test_open_session_within_budget_reserves_quota(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    r = _open_session(client, a["worker_token"], a["id"], task_code="T2", size=5 * 1024 * 1024)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "open"
    assert body["task_bytes_remaining"] == 15 * 1024 * 1024  # T2 budget 20 MB - 5 MB reserved
    assert body["total_bytes_remaining"] == 115 * 1024 * 1024


def test_open_session_requires_worker_token(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    r = client.post("/uploads", json={
        "assessment_id": a["id"], "task_code": "T1", "kind": "photo", "mime": "image/jpeg", "claimed_size_bytes": 10,
    })
    assert r.status_code == 401


def test_open_session_over_task_budget_is_rejected(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    r = _open_session(client, a["worker_token"], a["id"], task_code="T1", size=16 * 1024 * 1024)
    assert r.status_code == 409


def test_two_open_sessions_on_same_task_cannot_jointly_exceed_its_budget(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    first = _open_session(client, a["worker_token"], a["id"], task_code="T1", size=10 * 1024 * 1024)
    assert first.status_code == 201
    second = _open_session(client, a["worker_token"], a["id"], task_code="T1", size=10 * 1024 * 1024)
    assert second.status_code == 409  # 10 + 10 > 15 MB T1 budget, even though neither alone exceeds it


def test_reject_invalid_kind(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    r = client.post("/uploads", json={
        "assessment_id": a["id"], "task_code": "T1", "kind": "audio", "mime": "image/jpeg", "claimed_size_bytes": 10,
    }, headers={WT_HEADER: a["worker_token"]})
    assert r.status_code == 422


def test_reject_mime_kind_mismatch(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    r = client.post("/uploads", json={
        "assessment_id": a["id"], "task_code": "T1", "kind": "photo", "mime": "video/mp4", "claimed_size_bytes": 10,
    }, headers={WT_HEADER: a["worker_token"]})
    assert r.status_code == 422


def test_reject_zero_and_negative_claimed_size(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    for size in (0, -5):
        r = client.post("/uploads", json={
            "assessment_id": a["id"], "task_code": "T1", "kind": "photo", "mime": "image/jpeg", "claimed_size_bytes": size,
        }, headers={WT_HEADER: a["worker_token"]})
        assert r.status_code == 422, (size, r.text)


def test_normal_upload_and_completion_returns_matching_receipt(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    data = b"a" * 1000 + b"b" * 1000  # two "chunks"
    opened = _open_session(client, a["worker_token"], a["id"], size=len(data)).json()
    token = a["worker_token"]

    ack0 = client.put(f"/uploads/{opened['id']}/chunks/0", content=data[:1000], headers={WT_HEADER: token})
    assert ack0.status_code == 200, ack0.text
    assert ack0.json() == {"chunk_index": 0, "received_bytes": 1000, "next_chunk_index": 1, "status": "open"}

    ack1 = client.put(f"/uploads/{opened['id']}/chunks/1", content=data[1000:], headers={WT_HEADER: token})
    assert ack1.json()["received_bytes"] == 2000

    expected_sha = hashlib.sha256(data).hexdigest()
    done = client.post(f"/uploads/{opened['id']}/complete", json={"client_sha256": expected_sha}, headers={WT_HEADER: token})
    assert done.status_code == 200, done.text
    receipt = done.json()
    assert receipt["sha256"] == expected_sha
    assert receipt["byte_count"] == 2000
    assert receipt["storage_status"] == "stored"
    assert receipt["kind"] == "video"
    assert receipt["mime"] == "video/mp4"


def test_interrupted_upload_can_resume_from_reported_offset(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    data = b"x" * 300
    opened = _open_session(client, token, a["id"], size=len(data)).json()

    r0 = client.put(f"/uploads/{opened['id']}/chunks/0", content=data[:100], headers={WT_HEADER: token})
    assert r0.status_code == 200, r0.text
    # "client restarts" -- forgets its local state, asks the server for status
    status = client.get(f"/uploads/{opened['id']}", headers={WT_HEADER: token})
    assert status.status_code == 200
    assert status.json()["received_bytes"] == 100
    assert status.json()["next_chunk_index"] == 1

    r1 = client.put(f"/uploads/{opened['id']}/chunks/1", content=data[100:200], headers={WT_HEADER: token})
    r2 = client.put(f"/uploads/{opened['id']}/chunks/2", content=data[200:], headers={WT_HEADER: token})
    assert r1.status_code == 200 and r2.status_code == 200

    sha = hashlib.sha256(data).hexdigest()
    done = client.post(f"/uploads/{opened['id']}/complete", json={"client_sha256": sha}, headers={WT_HEADER: token})
    assert done.status_code == 200
    assert done.json()["byte_count"] == 300


def test_replaying_the_last_acked_chunk_is_idempotent(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    data = b"z" * 20
    opened = _open_session(client, token, a["id"], size=len(data)).json()

    first = client.put(f"/uploads/{opened['id']}/chunks/0", content=data, headers={WT_HEADER: token})
    assert first.status_code == 200, first.text
    replay = client.put(f"/uploads/{opened['id']}/chunks/0", content=data, headers={WT_HEADER: token})
    assert replay.status_code == 200
    assert replay.json()["received_bytes"] == 20  # not 40 -- bytes were not appended twice


def test_out_of_order_chunk_is_rejected(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    opened = _open_session(client, token, a["id"], size=100).json()
    r = client.put(f"/uploads/{opened['id']}/chunks/3", content=b"x" * 10, headers={WT_HEADER: token})
    assert r.status_code == 409


def test_chunk_that_would_exceed_declared_total_is_rejected(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    opened = _open_session(client, token, a["id"], size=10).json()
    r = client.put(f"/uploads/{opened['id']}/chunks/0", content=b"x" * 11, headers={WT_HEADER: token})
    assert r.status_code == 409


def test_complete_with_incorrect_total_size_is_rejected(client, imported_pack, worker):
    """Client claims 100 bytes but only ever uploads 50, then tries to complete early."""
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    data = b"y" * 50
    opened = _open_session(client, token, a["id"], size=100).json()
    setup = client.put(f"/uploads/{opened['id']}/chunks/0", content=data, headers={WT_HEADER: token})
    assert setup.status_code == 200, setup.text

    sha = hashlib.sha256(data).hexdigest()
    r = client.post(f"/uploads/{opened['id']}/complete", json={"client_sha256": sha}, headers={WT_HEADER: token})
    assert r.status_code == 409
    assert "size mismatch" in r.json()["detail"]


def test_complete_with_incorrect_hash_is_rejected_even_with_correct_size(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    data = b"real data"
    opened = _open_session(client, token, a["id"], size=len(data)).json()
    setup = client.put(f"/uploads/{opened['id']}/chunks/0", content=data, headers={WT_HEADER: token})
    assert setup.status_code == 200, setup.text

    wrong_sha = hashlib.sha256(b"different data!!").hexdigest()
    r = client.post(f"/uploads/{opened['id']}/complete", json={"client_sha256": wrong_sha}, headers={WT_HEADER: token})
    assert r.status_code == 409
    assert "hash mismatch" in r.json()["detail"]
    # session stays open so the client can retry without losing its quota reservation
    status = client.get(f"/uploads/{opened['id']}", headers={WT_HEADER: token})
    assert status.json()["status"] == "open"


def test_duplicate_complete_call_returns_same_receipt_not_a_new_evidence_item(client, imported_pack, worker, db_session):
    from server.app import models

    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    data = b"idempotent bytes"
    opened = _open_session(client, token, a["id"], size=len(data)).json()
    setup = client.put(f"/uploads/{opened['id']}/chunks/0", content=data, headers={WT_HEADER: token})
    assert setup.status_code == 200, setup.text
    sha = hashlib.sha256(data).hexdigest()

    first = client.post(f"/uploads/{opened['id']}/complete", json={"client_sha256": sha}, headers={WT_HEADER: token})
    second = client.post(f"/uploads/{opened['id']}/complete", json={"client_sha256": sha}, headers={WT_HEADER: token})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["evidence_id"] == second.json()["evidence_id"]
    assert first.json() == second.json()

    count = db_session.query(models.EvidenceItem).filter_by(
        assessment_task_id=db_session.get(models.UploadSession, opened["id"]).assessment_task_id
    ).count()
    assert count == 1


def test_quota_released_is_consumed_by_evidence_after_completion(client, imported_pack, worker):
    """Once a session completes, its reservation converts into real
    EvidenceItem bytes -- the remaining-budget accounting shouldn't double
    count or lose track across that transition."""
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    data = b"q" * (5 * 1024 * 1024)
    opened = _open_session(client, token, a["id"], task_code="T2", size=len(data)).json()
    _upload_all_chunks(client, token, opened["id"], data)
    sha = hashlib.sha256(data).hexdigest()
    completed = client.post(f"/uploads/{opened['id']}/complete", json={"client_sha256": sha}, headers={WT_HEADER: token})
    assert completed.status_code == 200, completed.text

    status = client.get(f"/assessments/{a['id']}", headers={WT_HEADER: token})
    task = next(t for t in status.json()["tasks"] if t["task_code"] == "T2")
    assert task["bytes_used"] == 5 * 1024 * 1024

    # Opening a second session on T2 only has budget - already-used room.
    second = _open_session(client, token, a["id"], task_code="T2", size=16 * 1024 * 1024)
    assert second.status_code == 409  # 20 MB budget - 5 MB used = 15 MB remaining, 16 MB requested


def _fail_without_postgres(db_session):
    if db_session.bind.dialect.name != "postgresql":
        pytest.fail(
            "this test requires TEST_DATABASE_URL to point at a real PostgreSQL database -- "
            "SQLite has no row-level locking, so the SELECT FOR UPDATE guarantee cannot be "
            "demonstrated against it. See server/README.md for how to run against the "
            "dockerized Postgres."
        )


def _two_sessions_against(db_session):
    """Two independent engines/sessions against the same real database, like
    two real concurrent requests -- mirrors test_jobs.py's
    test_concurrent_claims_never_double_process pattern."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # NOT str(url) -- that redacts the password.
    url = db_session.bind.url.render_as_string(hide_password=False)
    engine_a = create_engine(url)
    engine_b = create_engine(url)
    return engine_a, engine_b, sessionmaker(bind=engine_a), sessionmaker(bind=engine_b)


def test_concurrent_reservations_on_same_task_never_jointly_exceed_its_budget(client, db_session, imported_pack, worker):
    """Real two-thread, two-connection proof that POST /uploads locks a
    stable parent row before reserving quota (routers/uploads.py's
    open_upload_session) -- unlike
    test_two_open_sessions_on_same_task_cannot_jointly_exceed_its_budget
    above, which only proves the check holds across two *sequential* calls,
    this fires both at once and proves the race is actually closed."""
    _fail_without_postgres(db_session)
    from server.app import schemas
    from server.app.routers import uploads as uploads_router

    a = _new_assessment(client, imported_pack, worker)  # T1 budget 15 MB
    token = a["worker_token"]
    engine_a, engine_b, SessionA, SessionB = _two_sessions_against(db_session)

    results = {}
    barrier = threading.Barrier(2)

    def _reserve(session_factory, key):
        barrier.wait()
        s = session_factory()
        try:
            body = schemas.UploadSessionCreate(
                assessment_id=a["id"], task_code="T1", kind="video", mime="video/mp4",
                claimed_size_bytes=10 * 1024 * 1024,
            )
            out = uploads_router.open_upload_session(body=body, x_worker_token=token, db=s)
            results[key] = ("ok", out.status)
        except HTTPException as e:
            results[key] = ("error", e.status_code)
        finally:
            s.close()

    t_a = threading.Thread(target=_reserve, args=(SessionA, "a"))
    t_b = threading.Thread(target=_reserve, args=(SessionB, "b"))
    t_a.start()
    t_b.start()
    t_a.join(timeout=30)
    t_b.join(timeout=30)
    engine_a.dispose()
    engine_b.dispose()

    outcomes = [results["a"], results["b"]]
    successes = [o for o in outcomes if o[0] == "ok"]
    rejections = [o for o in outcomes if o == ("error", 409)]
    assert len(successes) == 1, f"expected exactly one 201 (reservation accepted), got {outcomes}"
    assert len(rejections) == 1, f"expected exactly one 409 (reservation rejected), got {outcomes}"


def test_concurrent_identical_chunk_puts_never_double_append(client, db_session, imported_pack, worker):
    """Two threads PUT the exact same chunk_index=0 at once. Without the row
    lock in _put_chunk, both could read next_chunk_index=0 before either
    commits, both treat it as new (not a replay), and both append to the
    storage file -- corrupting it -- even though one would then fail a
    unique-constraint insert on upload_chunks. With the lock, the second
    thread blocks, then (seeing committed state) correctly recognises its
    index as an already-received replay and skips the append entirely."""
    _fail_without_postgres(db_session)
    from server.app import models
    from server.app.routers.uploads import _put_chunk

    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    data = b"x" * 20
    opened = _open_session(client, token, a["id"], size=len(data)).json()
    engine_a, engine_b, SessionA, SessionB = _two_sessions_against(db_session)

    results = {}
    barrier = threading.Barrier(2)

    def _put(session_factory, key):
        barrier.wait()
        s = session_factory()
        try:
            ack = _put_chunk(opened["id"], 0, data, token, s)
            results[key] = ("ok", ack.received_bytes)
        except HTTPException as e:
            results[key] = ("error", e.status_code)
        finally:
            s.close()

    t_a = threading.Thread(target=_put, args=(SessionA, "a"))
    t_b = threading.Thread(target=_put, args=(SessionB, "b"))
    t_a.start()
    t_b.start()
    t_a.join(timeout=30)
    t_b.join(timeout=30)
    engine_a.dispose()
    engine_b.dispose()

    assert results["a"] == ("ok", len(data)), results
    assert results["b"] == ("ok", len(data)), results

    session = db_session.get(models.UploadSession, opened["id"])
    db_session.refresh(session)
    assert session.received_bytes == len(data), "bytes were appended more than once"
    chunk_count = db_session.query(models.UploadChunk).filter_by(
        upload_session_id=opened["id"], chunk_index=0
    ).count()
    assert chunk_count == 1


def test_concurrent_complete_calls_never_create_two_evidence_items(client, db_session, imported_pack, worker):
    """Two threads call POST .../complete on the same fully-uploaded session
    at once. Without the row lock, both could read status="open" before
    either commits and both create an EvidenceItem; with it, the second
    blocks, then sees status="completed" and returns the idempotent receipt
    instead of creating a second one."""
    _fail_without_postgres(db_session)
    from server.app import models, schemas
    from server.app.routers.uploads import complete_upload

    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    data = b"concurrent complete bytes"
    opened = _open_session(client, token, a["id"], size=len(data)).json()
    _upload_all_chunks(client, token, opened["id"], data)
    sha = hashlib.sha256(data).hexdigest()
    engine_a, engine_b, SessionA, SessionB = _two_sessions_against(db_session)

    results = {}
    barrier = threading.Barrier(2)

    def _complete(session_factory, key):
        barrier.wait()
        s = session_factory()
        try:
            receipt = complete_upload(opened["id"], schemas.UploadCompleteRequest(client_sha256=sha), token, s)
            results[key] = ("ok", receipt.evidence_id)
        except HTTPException as e:
            results[key] = ("error", e.status_code)
        finally:
            s.close()

    t_a = threading.Thread(target=_complete, args=(SessionA, "a"))
    t_b = threading.Thread(target=_complete, args=(SessionB, "b"))
    t_a.start()
    t_b.start()
    t_a.join(timeout=30)
    t_b.join(timeout=30)
    engine_a.dispose()
    engine_b.dispose()

    assert results["a"][0] == "ok" and results["b"][0] == "ok", results
    assert results["a"][1] == results["b"][1], "two different EvidenceItems were created for one completion"

    task_id = db_session.get(models.UploadSession, opened["id"]).assessment_task_id
    count = db_session.query(models.EvidenceItem).filter_by(assessment_task_id=task_id).count()
    assert count == 1


def test_evidence_finalisation_and_job_creation_are_atomic(client, db_session, imported_pack, worker, monkeypatch):
    """If enqueueing the verification job blows up, the whole completion
    must roll back -- no EvidenceItem, no task/assessment byte-counter
    update, no session status change. Proves complete_upload folds evidence
    finalisation and job creation into one transaction (jobs.enqueue(...,
    commit=False) followed by a single db.commit())."""
    from server.app import models
    from server.app.routers import uploads as uploads_router

    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    data = b"atomicity check bytes"
    opened = _open_session(client, token, a["id"], task_code="T1", size=len(data)).json()
    _upload_all_chunks(client, token, opened["id"], data)
    sha = hashlib.sha256(data).hexdigest()

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated enqueue failure")

    monkeypatch.setattr(uploads_router.jobs, "enqueue", _boom)

    with pytest.raises(RuntimeError, match="simulated enqueue failure"):
        client.post(f"/uploads/{opened['id']}/complete", json={"client_sha256": sha}, headers={WT_HEADER: token})

    db_session.rollback()
    session = db_session.get(models.UploadSession, opened["id"])
    db_session.refresh(session)
    assert session.status == "open", "session must not be marked completed if the job enqueue failed"
    task = db_session.get(models.AssessmentTask, session.assessment_task_id)
    db_session.refresh(task)
    assert task.bytes_used == 0, "task byte counter must not be updated if the transaction rolled back"
    count = db_session.query(models.EvidenceItem).filter_by(assessment_task_id=task.id).count()
    assert count == 0, "no EvidenceItem must exist if the completion transaction rolled back"


def test_completed_upload_appears_as_an_evidence_receipt_on_assessment_detail(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    data = b"evidence bytes for the dashboard"
    opened = _open_session(client, token, a["id"], task_code="T3", mime="image/jpeg", kind="photo", size=len(data)).json()
    _upload_all_chunks(client, token, opened["id"], data)
    sha = hashlib.sha256(data).hexdigest()
    receipt = client.post(f"/uploads/{opened['id']}/complete", json={"client_sha256": sha}, headers={WT_HEADER: token}).json()

    detail = client.get(f"/assessments/{a['id']}", headers={WT_HEADER: token}).json()
    t3 = next(t for t in detail["tasks"] if t["task_code"] == "T3")
    assert len(t3["evidence"]) == 1
    assert t3["evidence"][0]["id"] == receipt["evidence_id"]
    assert t3["evidence"][0]["sha256"] == sha
    assert t3["evidence"][0]["kind"] == "photo"
