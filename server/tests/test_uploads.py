"""Resumable upload protocol tests. See server/app/routers/uploads.py's
module docstring for the ordered-sequential-chunks protocol this exercises.
"""
import hashlib

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
