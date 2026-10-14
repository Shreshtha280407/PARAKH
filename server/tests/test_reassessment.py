"""P7 task-specific reassessment requests + versioned resubmission -- the
dashboard -> phone -> dashboard loop. See routers/reassessment.py,
routers/uploads.py's _maybe_complete_manifest/open_upload_session,
docs/gates/P7.md section 3.

Reuses test_sync.py's real P5-shaped signed-manifest helpers (same
envelope format a real Android device produces) rather than a parallel
fixture -- the whole point of this design is that it rides the exact same
protocol, not a new one.
"""
import hashlib

from server.tests.test_sync import (
    _canonical_manifest_bytes,
    _gen_keypair,
    _item,
    _sign_envelope,
    _upload_and_complete,
)

WT_HEADER = "X-Worker-Token"
ASSESSOR_PASSWORD = "correct horse battery staple"

TASKS = ["T1", "T2", "T3", "T4", "T5"]


def _new_assessment(client, imported_pack, worker):
    return client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()


def _full_v1_sync_and_submit(client, imported_pack, worker, revision_id="rev-1"):
    """Seal+sync a real, complete 5-task package and submit it -- the
    baseline every reassessment test starts from. Returns
    (assessment_json, token, priv, pub_b64, {task_code: (evidence_id, bytes)})."""
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    priv, pub_b64 = _gen_keypair()

    by_task = {}
    items = []
    task_totals = {}
    for i, task in enumerate(TASKS):
        data = f"evidence for {task} v1".encode() * (50 + i)
        evidence_id = f"ev-{task.lower()}-v1"
        kind = "video" if task == "T2" else "photo"
        mime = "video/mp4" if kind == "video" else "image/jpeg"
        items.append(_item(evidence_id, task, kind, data, mime))
        task_totals[task] = len(data)
        by_task[task] = (evidence_id, data, kind, mime)

    canonical = _canonical_manifest_bytes(a["id"], revision_id, items, task_totals, sum(task_totals.values()))
    envelope = _sign_envelope(priv, pub_b64, canonical)
    _, manifest_complete = _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id=revision_id)
    assert manifest_complete.status_code == 200, manifest_complete.text

    for task, (evidence_id, data, kind, mime) in by_task.items():
        _, complete = _upload_and_complete(
            client, token, a["id"], data, target="evidence", task_code=task, kind=kind, mime=mime,
            revision_id=revision_id, client_evidence_id=evidence_id,
        )
        assert complete.status_code == 200, complete.text

    submitted = client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: token})
    assert submitted.status_code == 200, submitted.text

    return a, token, priv, pub_b64, by_task


def _request_reassessment(client, assessment_id, assessor_headers, task_codes=("T4",), reason="evidence unclear", instructions="retake T4 with the board fully visible"):
    return client.post(f"/assessments/{assessment_id}/reassessment-requests", json={
        "task_codes": list(task_codes), "reason": reason, "capture_instructions": instructions,
    }, headers=assessor_headers)


def _start_review_and_score_all(client, assessment_id, assessor_headers, level=3):
    client.post(f"/assessments/{assessment_id}/start-review", headers=assessor_headers)
    items = client.get(f"/assessments/{assessment_id}/review", headers=assessor_headers).json()
    for item in items:
        client.put(f"/assessments/{assessment_id}/review", json={
            "pc_full_id": item["pc_full_id"], "score_level": level,
            "evidence_status": "DEMONSTRATED", "expected_version": 0,
        }, headers=assessor_headers)
    return items


# ---- request creation ----

def test_create_reassessment_request_requires_in_review_or_submitted(client, imported_pack, worker, assessor_headers):
    a = _new_assessment(client, imported_pack, worker)  # draft
    r = _request_reassessment(client, a["id"], assessor_headers)
    assert r.status_code == 409


def test_create_reassessment_request_requires_assessor_role(client, imported_pack, worker, assessor_headers):
    a, token, *_ = _full_v1_sync_and_submit(client, imported_pack, worker)
    r = client.post(f"/assessments/{a['id']}/reassessment-requests", json={
        "task_codes": ["T4"], "reason": "x", "capture_instructions": "y",
    })
    assert r.status_code == 401


def test_create_reassessment_request_blank_reason_rejected_422(client, imported_pack, worker, assessor_headers):
    a, token, *_ = _full_v1_sync_and_submit(client, imported_pack, worker)
    r = _request_reassessment(client, a["id"], assessor_headers, reason="   ")
    assert r.status_code == 422


def test_create_reassessment_request_blank_capture_instructions_rejected_422(client, imported_pack, worker, assessor_headers):
    a, token, *_ = _full_v1_sync_and_submit(client, imported_pack, worker)
    r = _request_reassessment(client, a["id"], assessor_headers, instructions="")
    assert r.status_code == 422


def test_create_reassessment_request_unknown_task_code_rejected(client, imported_pack, worker, assessor_headers):
    a, token, *_ = _full_v1_sync_and_submit(client, imported_pack, worker)
    # Rejected by schema validation (T1-T5 is the only valid domain for this
    # single fixed pack) before it would even reach the router's own
    # defense-in-depth "does this task exist on this assessment" check.
    r = _request_reassessment(client, a["id"], assessor_headers, task_codes=("T9",))
    assert r.status_code == 422


def test_create_reassessment_request_sets_needs_reassessment_and_bumps_revision(client, imported_pack, worker, assessor_headers):
    a, token, *_ = _full_v1_sync_and_submit(client, imported_pack, worker)
    r = _request_reassessment(client, a["id"], assessor_headers)
    assert r.status_code == 201, r.text
    assert r.json()["revision_number"] == 2
    assert r.json()["status"] == "pending"

    detail = client.get(f"/assessments/{a['id']}", headers=assessor_headers).json()
    assert detail["status"] == "needs_reassessment"
    assert detail["revision_number"] == 2


def test_second_pending_request_rejected_while_first_unresolved(client, imported_pack, worker, assessor_headers):
    a, token, *_ = _full_v1_sync_and_submit(client, imported_pack, worker)
    first = _request_reassessment(client, a["id"], assessor_headers, task_codes=("T4",))
    assert first.status_code == 201
    second = _request_reassessment(client, a["id"], assessor_headers, task_codes=("T2",))
    assert second.status_code == 409


# ---- task-only reopening is enforced SERVER-SIDE on upload ----

def test_worker_cannot_open_evidence_session_for_a_task_not_reopened(client, imported_pack, worker, assessor_headers):
    a, token, priv, pub_b64, by_task = _full_v1_sync_and_submit(client, imported_pack, worker)
    _request_reassessment(client, a["id"], assessor_headers, task_codes=("T4",))

    r = client.post("/uploads", json={
        "assessment_id": a["id"], "target": "evidence", "task_code": "T1", "kind": "photo",
        "mime": "image/jpeg", "claimed_size_bytes": 10, "revision_id": "rev-2", "client_evidence_id": "ev-t1-sneaky",
    }, headers={WT_HEADER: token})
    assert r.status_code == 409
    assert "not reopened" in r.text.lower() or "locked" in r.text.lower()


def test_worker_can_open_evidence_session_for_the_reopened_task(client, imported_pack, worker, assessor_headers):
    a, token, priv, pub_b64, by_task = _full_v1_sync_and_submit(client, imported_pack, worker)
    _request_reassessment(client, a["id"], assessor_headers, task_codes=("T4",))

    # Manifest-before-evidence ordering (same P6 rule as the very first
    # sync) applies to every revision -- send the v2 manifest first.
    t4_new = ("ev-t4-v2", b"new T4 evidence" * 60, "photo", "image/jpeg")
    manifest_complete, _ = _seal_and_sync_v2(client, token, a["id"], by_task, {}, priv, pub_b64)
    assert manifest_complete.status_code != 409

    r = client.post("/uploads", json={
        "assessment_id": a["id"], "target": "evidence", "task_code": "T4", "kind": "photo",
        "mime": "image/jpeg", "claimed_size_bytes": len(t4_new[1]), "revision_id": "rev-2", "client_evidence_id": t4_new[0],
    }, headers={WT_HEADER: token})
    assert r.status_code == 201, r.text


def test_manifest_cannot_open_without_an_open_reassessment_revision(client, imported_pack, worker, assessor_headers):
    """needs_reassessment status alone (e.g. via the OLD whole-assessment
    /decision endpoint) must not let uploads resume -- only an actual open
    AssessmentRevision (created by POST .../reassessment-requests) does."""
    a, token, *_ = _full_v1_sync_and_submit(client, imported_pack, worker)
    client.post(f"/assessments/{a['id']}/start-review", headers=assessor_headers)
    client.post(f"/assessments/{a['id']}/decision", json={"decision": "needs_reassessment"}, headers=assessor_headers)

    r = client.post("/uploads", json={
        "assessment_id": a["id"], "target": "manifest", "claimed_size_bytes": 10, "revision_id": "rev-2",
    }, headers={WT_HEADER: token})
    assert r.status_code == 409


# ---- the full v1 -> v2 loop: inherited evidence, new evidence, resubmit ----

def _seal_and_sync_v2(client, token, assessment_id, by_task, changed_tasks: dict, priv, pub_b64, revision_id="rev-2"):
    """Build a FULL v2 manifest: unchanged tasks re-declare their v1
    evidenceId/sha256/bytes EXACTLY (inherited by reference, never
    re-uploaded); changed_tasks gets brand-new items that ARE uploaded.
    This mirrors exactly what the real Android client does once its local
    vault copy of the unchanged items has already been deleted (P6) --
    see docs/gates/P7.md section 3."""
    items = []
    task_totals = {}
    for task, (evidence_id, data, kind, mime) in by_task.items():
        if task in changed_tasks:
            continue
        items.append(_item(evidence_id, task, kind, data, mime))
        task_totals[task] = len(data)

    new_uploads = {}
    for task, (new_evidence_id, new_data, new_kind, new_mime) in changed_tasks.items():
        items.append(_item(new_evidence_id, task, new_kind, new_data, new_mime))
        task_totals[task] = len(new_data)
        new_uploads[task] = (new_evidence_id, new_data, new_kind, new_mime)

    # Reuses v1's own keypair -- the TOFU device-key pin (Assessment.
    # device_public_key_b64) applies for the lifetime of the assessment,
    # not just its first manifest: a real phone's Android Keystore signing
    # key is stable across app restarts and reassessment cycles, so a v2
    # manifest from a genuinely different key would (correctly) be rejected
    # just like any other signer mismatch.
    canonical = _canonical_manifest_bytes(assessment_id, revision_id, items, task_totals, sum(task_totals.values()))
    envelope = _sign_envelope(priv, pub_b64, canonical)
    _, manifest_complete = _upload_and_complete(
        client, token, assessment_id, envelope, target="manifest", revision_id=revision_id,
    )
    if manifest_complete.status_code != 200:
        return manifest_complete, new_uploads

    for task, (evidence_id, data, kind, mime) in new_uploads.items():
        _, complete = _upload_and_complete(
            client, token, assessment_id, data, target="evidence", task_code=task, kind=kind, mime=mime,
            revision_id=revision_id, client_evidence_id=evidence_id,
        )
        assert complete.status_code == 200, complete.text

    return manifest_complete, new_uploads


def test_v2_inherits_unchanged_tasks_without_reupload_and_completes(client, imported_pack, worker, assessor_headers):
    a, token, priv, pub_b64, by_task = _full_v1_sync_and_submit(client, imported_pack, worker)
    _request_reassessment(client, a["id"], assessor_headers, task_codes=("T4",))

    t4_new = ("ev-t4-v2", b"brand new T4 evidence v2" * 60, "photo", "image/jpeg")
    manifest_complete, _ = _seal_and_sync_v2(client, token, a["id"], by_task, {"T4": t4_new}, priv, pub_b64)
    assert manifest_complete.status_code == 200, manifest_complete.text
    assert manifest_complete.json()["status"] == "received"

    status = client.get(f"/assessments/{a['id']}/sync-status", params={"revision_id": "rev-2"}, headers={WT_HEADER: token}).json()
    assert status["manifest_state"] == "complete"
    assert status["all_items_verified"] is True
    # T1/T2/T3/T5 verified WITHOUT any new upload session having been
    # opened for them in rev-2 -- only T4 was actually uploaded.
    states = {i["client_evidence_id"]: i["state"] for i in status["items"]}
    assert states["ev-t1-v1"] == "verified"
    assert states["ev-t4-v2"] == "verified"


def test_v2_resubmit_moves_back_to_submitted_and_fulfils_the_request(client, imported_pack, worker, assessor_headers):
    a, token, priv, pub_b64, by_task = _full_v1_sync_and_submit(client, imported_pack, worker)
    request = _request_reassessment(client, a["id"], assessor_headers, task_codes=("T4",)).json()

    t4_new = ("ev-t4-v2", b"brand new T4 evidence v2" * 60, "photo", "image/jpeg")
    manifest_complete, _ = _seal_and_sync_v2(client, token, a["id"], by_task, {"T4": t4_new}, priv, pub_b64)
    assert manifest_complete.status_code == 200

    submit = client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: token})
    assert submit.status_code == 200, submit.text
    assert submit.json()["status"] == "submitted"

    requests = client.get(f"/assessments/{a['id']}/reassessment-requests", headers=assessor_headers).json()
    fulfilled = next(r for r in requests if r["id"] == request["id"])
    assert fulfilled["status"] == "fulfilled"

    revisions = client.get(f"/assessments/{a['id']}/revisions", headers=assessor_headers).json()
    v2 = next(r for r in revisions if r["revision_number"] == 2)
    assert v2["status"] == "submitted"
    assert v2["reopened_task_codes"] == ["T4"]


def test_v1_and_v2_evidence_both_visible_current_vs_historical_distinguished(client, imported_pack, worker, assessor_headers):
    a, token, priv, pub_b64, by_task = _full_v1_sync_and_submit(client, imported_pack, worker)
    _request_reassessment(client, a["id"], assessor_headers, task_codes=("T4",))
    t4_new = ("ev-t4-v2", b"brand new T4 evidence v2" * 60, "photo", "image/jpeg")
    _seal_and_sync_v2(client, token, a["id"], by_task, {"T4": t4_new}, priv, pub_b64)
    client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: token})

    detail = client.get(f"/assessments/{a['id']}", headers=assessor_headers).json()
    t4_task = next(t for t in detail["tasks"] if t["task_code"] == "T4")
    assert len(t4_task["evidence"]) == 2  # the old v1 item AND the new v2 item both still exist
    new_sha256 = hashlib.sha256(t4_new[1]).hexdigest()
    old_item = next(e for e in t4_task["evidence"] if e["sha256"] != new_sha256)
    new_item = next(e for e in t4_task["evidence"] if e["sha256"] == new_sha256)
    assert old_item["is_current_revision"] is False
    assert old_item["revision_number"] == 1
    assert new_item["is_current_revision"] is True
    assert new_item["revision_number"] == 2

    # An UNCHANGED task's evidence stays current.
    t1_task = next(t for t in detail["tasks"] if t["task_code"] == "T1")
    assert len(t1_task["evidence"]) == 1
    assert t1_task["evidence"][0]["is_current_revision"] is True


# ---- security: inherited-item integrity + locked-task enforcement ----

def test_v2_manifest_with_mismatched_hash_for_an_inherited_item_is_rejected(client, imported_pack, worker, assessor_headers):
    a, token, priv, pub_b64, by_task = _full_v1_sync_and_submit(client, imported_pack, worker)
    _request_reassessment(client, a["id"], assessor_headers, task_codes=("T4",))

    # Rebuild T1's declared item with the SAME evidenceId but a DIFFERENT
    # (wrong) sha256/bytes -- simulates a buggy or malicious client trying
    # to slip a substituted "inherited" item past the server.
    t1_evidence_id, t1_data, t1_kind, t1_mime = by_task["T1"]
    items = [_item(t1_evidence_id, "T1", t1_kind, b"a completely different file", t1_mime)]
    for task in ("T2", "T3", "T5"):
        evidence_id, data, kind, mime = by_task[task]
        items.append(_item(evidence_id, task, kind, data, mime))
    t4_evidence_id, t4_data, t4_kind, t4_mime = "ev-t4-v2", b"new t4 data" * 60, "photo", "image/jpeg"
    items.append(_item(t4_evidence_id, "T4", t4_kind, t4_data, t4_mime))

    task_totals = {t: len(d) for t, (_, d, _, _) in by_task.items()}
    task_totals["T1"] = len(b"a completely different file")
    task_totals["T4"] = len(t4_data)

    canonical = _canonical_manifest_bytes(a["id"], "rev-2", items, task_totals, sum(task_totals.values()))
    envelope = _sign_envelope(priv, pub_b64, canonical)
    _, manifest_complete = _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id="rev-2")
    assert manifest_complete.status_code == 200  # manifest envelope itself is validly signed -- it's RECEIVED

    _, t4_complete = _upload_and_complete(
        client, token, a["id"], t4_data, target="evidence", task_code="T4", kind=t4_kind, mime=t4_mime,
        revision_id="rev-2", client_evidence_id=t4_evidence_id,
    )
    assert t4_complete.status_code == 200

    status = client.get(f"/assessments/{a['id']}/sync-status", params={"revision_id": "rev-2"}, headers={WT_HEADER: token}).json()
    assert status["manifest_state"] == "rejected"
    assert "does not match" in (status["manifest_rejection_reason"] or "").lower()


def test_v2_manifest_declaring_new_evidence_for_a_locked_task_is_rejected(client, imported_pack, worker, assessor_headers):
    """Belt-and-braces: even if a sneaky item for a locked task were
    declared in the manifest, open_upload_session already refuses a fresh
    session for it (see test above) -- so it can NEVER actually be
    uploaded, and the manifest can thus never reach 'complete' no matter
    what the dashboard/assessor does next. T4's own legitimate new item
    IS uploaded, proving the stall is specifically about the locked T1
    item, not a general failure."""
    a, token, priv, pub_b64, by_task = _full_v1_sync_and_submit(client, imported_pack, worker)
    _request_reassessment(client, a["id"], assessor_headers, task_codes=("T4",))  # ONLY T4 reopened

    t1_sneaky = ("ev-t1-sneaky", b"sneaky new T1 evidence" * 60, "photo", "image/jpeg")
    t4_new = ("ev-t4-v2", b"legit new T4 evidence" * 60, "photo", "image/jpeg")

    items = []
    task_totals = {}
    for task, (evidence_id, data, kind, mime) in by_task.items():
        if task in ("T1", "T4"):
            continue
        items.append(_item(evidence_id, task, kind, data, mime))
        task_totals[task] = len(data)
    items.append(_item(t1_sneaky[0], "T1", t1_sneaky[2], t1_sneaky[1], t1_sneaky[3]))
    task_totals["T1"] = len(t1_sneaky[1])
    items.append(_item(t4_new[0], "T4", t4_new[2], t4_new[1], t4_new[3]))
    task_totals["T4"] = len(t4_new[1])

    canonical = _canonical_manifest_bytes(a["id"], "rev-2", items, task_totals, sum(task_totals.values()))
    envelope = _sign_envelope(priv, pub_b64, canonical)
    _, manifest_complete = _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id="rev-2")
    assert manifest_complete.status_code == 200  # envelope itself verifies fine -- it's RECEIVED

    # T1 is locked -- open_upload_session refuses it outright (confirmed
    # separately above); only attempt the legitimate T4 upload here.
    t1_open = client.post("/uploads", json={
        "assessment_id": a["id"], "target": "evidence", "task_code": "T1", "kind": t1_sneaky[2], "mime": t1_sneaky[3],
        "claimed_size_bytes": len(t1_sneaky[1]), "revision_id": "rev-2", "client_evidence_id": t1_sneaky[0],
    }, headers={WT_HEADER: token})
    assert t1_open.status_code == 409

    _, t4_complete = _upload_and_complete(
        client, token, a["id"], t4_new[1], target="evidence", task_code="T4", kind=t4_new[2], mime=t4_new[3],
        revision_id="rev-2", client_evidence_id=t4_new[0],
    )
    assert t4_complete.status_code == 200, t4_complete.text

    t4_status = client.get(
        f"/assessments/{a['id']}/sync-status", params={"revision_id": "rev-2"}, headers={WT_HEADER: token},
    ).json()
    items_by_id = {i["client_evidence_id"]: i for i in t4_status["items"]}
    assert items_by_id[t4_new[0]]["state"] == "verified"
    assert items_by_id[t1_sneaky[0]]["state"] == "pending"  # declared, but can never be uploaded -- locked

    assert t4_status["manifest_state"] == "received"  # never 'complete': T1's declared item is permanently stuck
    assert t4_status["all_items_verified"] is False

    submit = client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: token})
    assert submit.status_code == 409


def test_cross_assessment_evidence_reference_never_resolves(client, imported_pack, worker, assessor_headers):
    """A manifest declaring an evidenceId that was never actually uploaded
    under THIS assessment's own tasks (e.g. copied from a different
    assessment) can never reach 'complete' -- the lookup is scoped to this
    assessment's own AssessmentTask rows by construction."""
    a, token, priv, pub_b64, by_task = _full_v1_sync_and_submit(client, imported_pack, worker)
    _request_reassessment(client, a["id"], assessor_headers, task_codes=("T1",))

    foreign_item = _item("ev-from-a-totally-different-assessment", "T1", "photo", b"foreign bytes", "image/jpeg")
    items = [foreign_item]
    for task in ("T2", "T3", "T4", "T5"):
        evidence_id, data, kind, mime = by_task[task]
        items.append(_item(evidence_id, task, kind, data, mime))
    task_totals = {t: len(d) for t, (_, d, _, _) in by_task.items()}
    task_totals["T1"] = len(b"foreign bytes")

    canonical = _canonical_manifest_bytes(a["id"], "rev-2", items, task_totals, sum(task_totals.values()))
    envelope = _sign_envelope(priv, pub_b64, canonical)
    _, manifest_complete = _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id="rev-2")
    assert manifest_complete.status_code == 200

    status = client.get(f"/assessments/{a['id']}/sync-status", params={"revision_id": "rev-2"}, headers={WT_HEADER: token}).json()
    assert status["all_items_verified"] is False
    assert status["manifest_state"] == "received"  # stuck, never completes -- no cross-assessment leak

    submit = client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: token})
    assert submit.status_code == 409


# ---- budget enforcement on the full revision snapshot ----

def test_oversized_declared_total_bytes_is_rejected_at_manifest_accept_time(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    priv, pub_b64 = _gen_keypair()
    data = b"small file"
    items = [_item("e1", "T1", "photo", data, "image/jpeg")]
    # Declares a grossly inflated total (the pack's budget is 120 MB) --
    # independent of any individual item's own (correct, small) byte count.
    canonical = _canonical_manifest_bytes(a["id"], "rev-1", items, {"T1": 200_000_000}, 200_000_000)
    envelope = _sign_envelope(priv, pub_b64, canonical)
    _, manifest_complete = _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id="rev-1")
    assert manifest_complete.status_code == 409
    assert "budget" in manifest_complete.text.lower()


def test_oversized_task_total_is_rejected_at_manifest_accept_time(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    priv, pub_b64 = _gen_keypair()
    data = b"small file"
    items = [_item("e1", "T1", "photo", data, "image/jpeg")]
    # T1's own budget is 15 MB (packs/ae-con-q0602/tasks.json) -- well under this.
    canonical = _canonical_manifest_bytes(a["id"], "rev-1", items, {"T1": 50_000_000}, 50_000_000)
    envelope = _sign_envelope(priv, pub_b64, canonical)
    _, manifest_complete = _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id="rev-1")
    assert manifest_complete.status_code == 409
    assert "budget" in manifest_complete.text.lower()


# ---- score provenance: affected PCs must be re-reviewed, not carried forward ----

def test_reopened_task_pcs_flagged_needs_review_and_block_sign_off(client, imported_pack, worker, assessor_headers):
    a, token, priv, pub_b64, by_task = _full_v1_sync_and_submit(client, imported_pack, worker)
    _start_review_and_score_all(client, a["id"], assessor_headers, level=3)

    review_before = client.get(f"/assessments/{a['id']}/review", headers=assessor_headers).json()
    t4_pcs = [i for i in review_before if i["pc_full_id"].startswith("CON/N0603.")]
    assert t4_pcs, "expected at least one T4 (CON/N0603) PC in the rubric"
    for i in t4_pcs:
        assert i["score"]["needs_review"] is False

    _request_reassessment(client, a["id"], assessor_headers, task_codes=("T4",))

    review_after = client.get(f"/assessments/{a['id']}/review", headers=assessor_headers).json()
    t4_after = [i for i in review_after if i["pc_full_id"].startswith("CON/N0603.")]
    assert all(i["score"]["needs_review"] is True for i in t4_after)
    non_t4_after = [i for i in review_after if not i["pc_full_id"].startswith("CON/N0603.")]
    assert all(i["score"]["needs_review"] is False for i in non_t4_after)  # untouched, clear provenance

    t4_new = ("ev-t4-v2", b"new T4 evidence for rescoring" * 60, "photo", "image/jpeg")
    _seal_and_sync_v2(client, token, a["id"], by_task, {"T4": t4_new}, priv, pub_b64)
    client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: token})
    client.post(f"/assessments/{a['id']}/start-review", headers=assessor_headers)

    # Signing off NOW must fail -- T4's PCs were reopened but never re-scored.
    r = client.post(f"/assessments/{a['id']}/sign-off", json={
        "password": ASSESSOR_PASSWORD, "final_recommendation": "RECOMMEND_CERTIFICATION",
    }, headers=assessor_headers)
    assert r.status_code == 409
    assert "re-review" in r.text.lower() or "reopened" in r.text.lower()

    # Re-score the affected PCs -- needs_review clears, sign-off now succeeds.
    review_now = client.get(f"/assessments/{a['id']}/review", headers=assessor_headers).json()
    for item in review_now:
        if item["pc_full_id"].startswith("CON/N0603."):
            client.put(f"/assessments/{a['id']}/review", json={
                "pc_full_id": item["pc_full_id"], "score_level": 3, "evidence_status": "DEMONSTRATED",
                "expected_version": item["score"]["version"],
            }, headers=assessor_headers)

    r2 = client.post(f"/assessments/{a['id']}/sign-off", json={
        "password": ASSESSOR_PASSWORD, "final_recommendation": "RECOMMEND_CERTIFICATION",
    }, headers=assessor_headers)
    assert r2.status_code == 201, r2.text
