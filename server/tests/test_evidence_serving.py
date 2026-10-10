"""Secure evidence content/thumbnail serving -- see
server/app/routers/evidence.py. Range-request support comes from
Starlette's FileResponse (no hand-rolled Range parsing to test here); what
matters is auth, the photo-direct/video-job split, and graceful fallback.
"""
import hashlib

WT_HEADER = "X-Worker-Token"


def _new_assessment(client, imported_pack, worker):
    return client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()


def _upload_photo(client, token, assessment_id, data: bytes, task_code="T1"):
    opened = client.post("/uploads", json={
        "assessment_id": assessment_id, "task_code": task_code, "kind": "photo", "mime": "image/jpeg",
        "claimed_size_bytes": len(data),
    }, headers={WT_HEADER: token}).json()
    client.put(f"/uploads/{opened['id']}/chunks/0", content=data, headers={WT_HEADER: token})
    sha = hashlib.sha256(data).hexdigest()
    receipt = client.post(f"/uploads/{opened['id']}/complete", json={"client_sha256": sha}, headers={WT_HEADER: token}).json()
    return receipt["evidence_id"]


def test_get_evidence_content_as_assessor(client, imported_pack, worker, assessor_headers):
    a = _new_assessment(client, imported_pack, worker)
    data = b"a real jpeg's worth of bytes"
    evidence_id = _upload_photo(client, a["worker_token"], a["id"], data)

    r = client.get(f"/assessments/{a['id']}/evidence/{evidence_id}/content", headers=assessor_headers)
    assert r.status_code == 200
    assert r.content == data
    assert r.headers["content-type"] == "image/jpeg"


def test_get_evidence_content_as_the_owning_worker(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    data = b"worker's own evidence bytes"
    evidence_id = _upload_photo(client, a["worker_token"], a["id"], data)

    r = client.get(f"/assessments/{a['id']}/evidence/{evidence_id}/content", headers={WT_HEADER: a["worker_token"]})
    assert r.status_code == 200
    assert r.content == data


def test_get_evidence_content_rejects_a_strangers_worker_token(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    data = b"private evidence"
    evidence_id = _upload_photo(client, a["worker_token"], a["id"], data)
    other = _new_assessment(client, imported_pack, worker)

    r = client.get(f"/assessments/{a['id']}/evidence/{evidence_id}/content", headers={WT_HEADER: other["worker_token"]})
    assert r.status_code == 401


def test_get_evidence_content_404s_for_evidence_on_a_different_assessment(client, imported_pack, worker, assessor_headers):
    a = _new_assessment(client, imported_pack, worker)
    b = _new_assessment(client, imported_pack, worker)
    evidence_id = _upload_photo(client, a["worker_token"], a["id"], b"bytes")

    r = client.get(f"/assessments/{b['id']}/evidence/{evidence_id}/content", headers=assessor_headers)
    assert r.status_code == 404


def test_photo_thumbnail_serves_the_original_bytes_directly(client, imported_pack, worker, assessor_headers):
    a = _new_assessment(client, imported_pack, worker)
    data = b"photo bytes used as their own thumbnail"
    evidence_id = _upload_photo(client, a["worker_token"], a["id"], data)

    r = client.get(f"/assessments/{a['id']}/evidence/{evidence_id}/thumbnail", headers=assessor_headers)
    assert r.status_code == 200
    assert r.content == data


def test_video_thumbnail_is_a_graceful_404_before_the_background_job_runs(client, imported_pack, worker, assessor_headers):
    """No worker process runs during these tests -- the thumbnail job stays
    queued, so this must be a clean 404 (not a 500) reporting that status."""
    a = _new_assessment(client, imported_pack, worker)
    data = b"fake video bytes, task T2 is video-only by pack convention or any task works here"
    opened = client.post("/uploads", json={
        "assessment_id": a["id"], "task_code": "T2", "kind": "video", "mime": "video/mp4",
        "claimed_size_bytes": len(data),
    }, headers={WT_HEADER: a["worker_token"]}).json()
    client.put(f"/uploads/{opened['id']}/chunks/0", content=data, headers={WT_HEADER: a["worker_token"]})
    sha = hashlib.sha256(data).hexdigest()
    receipt = client.post(
        f"/uploads/{opened['id']}/complete", json={"client_sha256": sha}, headers={WT_HEADER: a["worker_token"]}
    ).json()

    r = client.get(f"/assessments/{a['id']}/evidence/{receipt['evidence_id']}/thumbnail", headers=assessor_headers)
    assert r.status_code == 404
    assert "status: queued" in r.json()["detail"]
