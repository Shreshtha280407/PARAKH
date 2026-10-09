"""Upload SESSION tests only -- open-session quota checks. Chunk upload /
complete endpoints don't exist yet (out of P2 scope), so there is nothing to
test for byte transfer here."""


def test_open_upload_session_within_budget(client, imported_pack, worker):
    assessment = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    r = client.post("/uploads", json={
        "assessment_id": assessment["id"], "task_code": "T2", "claimed_size_bytes": 5 * 1024 * 1024,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "open"
    assert body["task_bytes_remaining"] == 15 * 1024 * 1024  # T2 budget 20 MB - 5 MB claimed
    assert body["total_bytes_remaining"] == 115 * 1024 * 1024


def test_open_upload_session_over_task_budget_is_rejected(client, imported_pack, worker):
    assessment = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    r = client.post("/uploads", json={
        "assessment_id": assessment["id"], "task_code": "T1", "claimed_size_bytes": 16 * 1024 * 1024,
    })
    assert r.status_code == 409


def test_two_open_sessions_on_the_same_task_cannot_jointly_exceed_its_budget(client, imported_pack, worker):
    assessment = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    first = client.post("/uploads", json={
        "assessment_id": assessment["id"], "task_code": "T1", "claimed_size_bytes": 10 * 1024 * 1024,
    })
    assert first.status_code == 201  # 10 MB of T1's 15 MB budget claimed, still open
    second = client.post("/uploads", json={
        "assessment_id": assessment["id"], "task_code": "T1", "claimed_size_bytes": 10 * 1024 * 1024,
    })
    assert second.status_code == 409  # 10 + 10 > 15 MB, even though neither alone exceeds it


def test_get_upload_session(client, imported_pack, worker):
    assessment = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    opened = client.post("/uploads", json={
        "assessment_id": assessment["id"], "task_code": "T3", "claimed_size_bytes": 1024,
    }).json()
    r = client.get(f"/uploads/{opened['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == opened["id"]


def test_evidence_metadata_and_open_upload_sessions_share_the_same_quota(client, imported_pack, worker):
    """An open upload session's claimed bytes must count against the same
    budget evidence metadata does -- otherwise the two paths could jointly
    double-book more than 120 MB."""
    assessment = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    # Record 10 MB of T1 evidence directly...
    r1 = client.post(f"/assessments/{assessment['id']}/evidence", json={
        "task_code": "T1", "kind": "photo", "mime": "image/jpeg", "declared_size_bytes": 10 * 1024 * 1024,
    })
    assert r1.status_code == 201
    # ...then try to open an upload session for another 10 MB on the same 15 MB task.
    r2 = client.post("/uploads", json={
        "assessment_id": assessment["id"], "task_code": "T1", "claimed_size_bytes": 10 * 1024 * 1024,
    })
    assert r2.status_code == 409
