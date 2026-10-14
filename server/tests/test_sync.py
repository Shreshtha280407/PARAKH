"""P6 resumable-sync protocol tests: P5 SignedManifestPackage verification,
revision/idempotency-key binding, evidence-vs-manifest cross-checking,
TOFU device-key pinning, revision supersession, and the submit gate that
keeps an unverified sync package out of the assessor queue.

See server/app/manifest_verify.py and routers/uploads.py's module docstring
for the exact protocol these tests exercise.
"""
import base64
import hashlib
import json
import threading

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

WT_HEADER = "X-Worker-Token"


# ---- real P5-shaped manifest/signature fixtures (mirrors
# apps/android/core/seal's SealManifest/ManifestSigner/SignedManifestPackage) ----

def _gen_keypair() -> tuple[ec.EllipticCurvePrivateKey, str]:
    priv = ec.generate_private_key(ec.SECP256R1())
    pub_der = priv.public_key().public_bytes(
        encoding=serialization.Encoding.DER, format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv, base64.b64encode(pub_der).decode()


def _canonical_manifest_bytes(
    assessment_id: int | str, revision_id: str, items: list[dict], task_totals: dict[str, int],
    assessment_total_bytes: int, declaration: dict | None = None,
) -> bytes:
    manifest = {
        "assessmentId": assessment_id,
        "revisionId": revision_id,
        "idempotencyKey": f"{assessment_id}:{revision_id}",
        "evidence": items,
        "taskTotals": [{"taskId": t, "finalBytes": b} for t, b in task_totals.items()],
        "assessmentFinalBytes": assessment_total_bytes,
    }
    if declaration is not None:
        manifest["declarationSummary"] = declaration
    return json.dumps(manifest, separators=(",", ":")).encode("utf-8")


def _sign_envelope(
    priv: ec.EllipticCurvePrivateKey, pub_b64: str, canonical_bytes: bytes,
    key_id: str = "test-key-1", algorithm: str = "SHA256withECDSA", signature_override: bytes | None = None,
) -> bytes:
    signature = signature_override if signature_override is not None else priv.sign(canonical_bytes, ec.ECDSA(hashes.SHA256()))
    envelope = {
        "manifestBase64": base64.b64encode(canonical_bytes).decode(),
        "signatureBase64": base64.b64encode(signature).decode(),
        "algorithm": algorithm,
        "signerKeyId": key_id,
        "signerPublicKeyBase64": pub_b64,
    }
    return json.dumps(envelope).encode("utf-8")


def _item(evidence_id: str, task_code: str, kind: str, data: bytes, mime: str) -> dict:
    return {
        "evidenceId": evidence_id, "taskId": task_code, "kind": kind,
        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "mimeType": mime,
        "processing": "SEALED",
    }


# ---- small helpers over the real HTTP API ----

def _new_assessment(client, imported_pack, worker):
    return client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()


def _open(client, token, assessment_id, **kwargs):
    body = {"assessment_id": assessment_id, "claimed_size_bytes": kwargs.pop("claimed_size_bytes")}
    body.update(kwargs)
    return client.post("/uploads", json=body, headers={WT_HEADER: token})


def _upload_and_complete(client, token, assessment_id, data: bytes, **open_kwargs):
    """Open a session, PUT the whole body as one chunk, complete it. Returns
    the (opened_json, complete_response)."""
    opened = _open(client, token, assessment_id, claimed_size_bytes=len(data), **open_kwargs)
    assert opened.status_code == 201, opened.text
    opened_json = opened.json()
    chunk = client.put(f"/uploads/{opened_json['id']}/chunks/0", content=data, headers={WT_HEADER: token})
    assert chunk.status_code == 200, chunk.text
    sha = hashlib.sha256(data).hexdigest()
    complete = client.post(f"/uploads/{opened_json['id']}/complete", json={"client_sha256": sha}, headers={WT_HEADER: token})
    return opened_json, complete


def _seal_and_sync_full_package(client, imported_pack, worker, revision_id="rev-1", declaration=None):
    """Build one real signed manifest + T1/T2 evidence, sync all of it, and
    return (assessment_json, token, priv_key, pub_b64, manifest_complete_response).
    The one happy-path fixture every other test in this file starts from or
    deviates from."""
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    priv, pub_b64 = _gen_keypair()

    t1_bytes = b"T1 safety ppe evidence jpeg bytes" * 100
    t2_bytes = b"T2 tool use evidence mp4 bytes" * 100
    items = [
        _item("ev-t1-photo", "T1", "photo", t1_bytes, "image/jpeg"),
        _item("ev-t2-video", "T2", "video", t2_bytes, "video/mp4"),
    ]
    canonical = _canonical_manifest_bytes(
        a["id"], revision_id, items, {"T1": len(t1_bytes), "T2": len(t2_bytes)},
        len(t1_bytes) + len(t2_bytes), declaration=declaration,
    )
    envelope = _sign_envelope(priv, pub_b64, canonical)
    _, manifest_complete = _upload_and_complete(
        client, token, a["id"], envelope, target="manifest", revision_id=revision_id,
    )
    assert manifest_complete.status_code == 200, manifest_complete.text

    _, t1_complete = _upload_and_complete(
        client, token, a["id"], t1_bytes, target="evidence", task_code="T1", kind="photo", mime="image/jpeg",
        revision_id=revision_id, client_evidence_id="ev-t1-photo",
    )
    assert t1_complete.status_code == 200, t1_complete.text
    _, t2_complete = _upload_and_complete(
        client, token, a["id"], t2_bytes, target="evidence", task_code="T2", kind="video", mime="video/mp4",
        revision_id=revision_id, client_evidence_id="ev-t2-video",
    )
    assert t2_complete.status_code == 200, t2_complete.text

    return a, token, priv, pub_b64, manifest_complete


# ---- happy path ----

def test_full_sync_happy_path_reaches_complete_and_allows_submit(client, imported_pack, worker):
    a, token, priv, pub_b64, manifest_complete = _seal_and_sync_full_package(
        client, imported_pack, worker,
        declaration={
            "matchResult": "PARTIAL", "overallCoverage": 0.6, "gapTaskCodes": ["T3", "T5"],
            "matchReasons": ["experience claimed below threshold for CON/N0603", "no prior training declared"],
        },
    )
    mbody = manifest_complete.json()
    assert mbody["status"] == "received"
    assert mbody["item_count"] == 2

    status = client.get(f"/assessments/{a['id']}/sync-status", headers={WT_HEADER: token})
    assert status.status_code == 200, status.text
    sbody = status.json()
    assert sbody["manifest_state"] == "complete"
    assert sbody["all_items_verified"] is True
    assert {i["client_evidence_id"]: i["state"] for i in sbody["items"]} == {
        "ev-t1-photo": "verified", "ev-t2-video": "verified",
    }

    detail = client.get(f"/assessments/{a['id']}", headers={WT_HEADER: token}).json()
    assert detail["declared_match_result"] == "PARTIAL"
    assert float(detail["declared_coverage_fraction"]) == pytest.approx(0.6)
    assert detail["declared_gap_task_codes"] == ["T3", "T5"]
    assert detail["declared_match_reasons"] == [
        "experience claimed below threshold for CON/N0603", "no prior training declared",
    ]
    assert detail["current_revision_id"] == "rev-1"

    submitted = client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: token})
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"


def test_submit_blocked_until_every_declared_item_is_verified(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    priv, pub_b64 = _gen_keypair()
    t1_bytes = b"only t1 evidence" * 50
    items = [_item("ev-t1-only", "T1", "photo", t1_bytes, "image/jpeg")]
    # Manifest declares TWO items but only one will ever be uploaded.
    items.append({
        "evidenceId": "ev-t2-missing", "taskId": "T2", "kind": "video",
        "bytes": 123, "sha256": "0" * 64, "mimeType": "video/mp4", "processing": "SEALED",
    })
    canonical = _canonical_manifest_bytes(a["id"], "rev-1", items, {"T1": len(t1_bytes), "T2": 123}, len(t1_bytes) + 123)
    envelope = _sign_envelope(priv, pub_b64, canonical)
    _, manifest_complete = _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id="rev-1")
    assert manifest_complete.status_code == 200

    _, t1_complete = _upload_and_complete(
        client, token, a["id"], t1_bytes, target="evidence", task_code="T1", kind="photo", mime="image/jpeg",
        revision_id="rev-1", client_evidence_id="ev-t1-only",
    )
    assert t1_complete.status_code == 200

    submit = client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: token})
    assert submit.status_code == 409, submit.text

    status = client.get(f"/assessments/{a['id']}/sync-status", headers={WT_HEADER: token}).json()
    assert status["all_items_verified"] is False
    assert status["manifest_state"] == "received"  # not yet "complete" -- one item still pending


# ---- manifest rejection paths ----

def test_manifest_with_tampered_bytes_fails_signature_verification(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    priv, pub_b64 = _gen_keypair()
    data = b"irrelevant"
    canonical = _canonical_manifest_bytes(a["id"], "rev-1", [_item("e1", "T1", "photo", data, "image/jpeg")], {"T1": len(data)}, len(data))
    signature = priv.sign(canonical, ec.ECDSA(hashes.SHA256()))
    tampered_canonical = canonical[:-1] + bytes([canonical[-1] ^ 0xFF])
    envelope = _sign_envelope(priv, pub_b64, tampered_canonical, signature_override=signature)

    _, complete = _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id="rev-1")
    assert complete.status_code == 409
    assert "rejected" in complete.text.lower()

    status = client.get(
        f"/assessments/{a['id']}/sync-status", params={"revision_id": "rev-1"}, headers={WT_HEADER: token},
    ).json()
    assert status["manifest_state"] == "rejected"
    assert status["manifest_rejection_reason"]


def test_manifest_unsupported_algorithm_rejected(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    priv, pub_b64 = _gen_keypair()
    data = b"x"
    canonical = _canonical_manifest_bytes(a["id"], "rev-1", [_item("e1", "T1", "photo", data, "image/jpeg")], {"T1": 1}, 1)
    envelope = _sign_envelope(priv, pub_b64, canonical, algorithm="HMAC-SHA256")
    _, complete = _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id="rev-1")
    assert complete.status_code == 409
    assert "algorithm" in complete.text.lower()


def test_manifest_first_ever_pins_client_assessment_id_regardless_of_server_integer_id(client, imported_pack, worker):
    # The manifest's assessmentId lives in the Android app's own local-UUID
    # identifier space, baked into the signed bytes at fully-offline seal
    # time, long before this server-side assessment row (with its own,
    # unrelated integer primary key) is ever bootstrapped. The very first
    # manifest for a fresh assessment must succeed and pin whatever client id
    # it carries -- it must NOT be compared against the server's own id.
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    priv, pub_b64 = _gen_keypair()
    data = b"x"
    client_local_id = "5856959b-434b-4f6a-b875-c401dc36d5ee"
    canonical = _canonical_manifest_bytes(client_local_id, "rev-1", [_item("e1", "T1", "photo", data, "image/jpeg")], {"T1": 1}, 1)
    envelope = _sign_envelope(priv, pub_b64, canonical)
    _, complete = _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id="rev-1")
    assert complete.status_code == 200, complete.text


def test_manifest_with_different_pinned_client_assessment_id_is_rejected(client, imported_pack, worker):
    # Once a client_assessment_id is pinned by the first manifest, a later
    # manifest for the SAME server-side assessment carrying a DIFFERENT
    # client id is a TOFU violation and must be rejected -- mirrors the
    # existing device-public-key pinning test below.
    a, token, priv, pub_b64, _ = _seal_and_sync_full_package(client, imported_pack, worker, revision_id="rev-1")

    data = b"y"
    different_client_id = "a-totally-different-local-uuid"
    canonical = _canonical_manifest_bytes(different_client_id, "rev-2", [_item("e2", "T1", "photo", data, "image/jpeg")], {"T1": 1}, 1)
    envelope = _sign_envelope(priv, pub_b64, canonical)
    _, complete = _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id="rev-2")
    assert complete.status_code == 409
    assert "client id" in complete.text.lower()


def test_manifest_conflicting_retry_with_different_bytes_is_refused(client, imported_pack, worker):
    a, token, priv, pub_b64, _ = _seal_and_sync_full_package(client, imported_pack, worker, revision_id="rev-1")

    other_priv, other_pub_b64 = _gen_keypair()
    data = b"a totally different manifest body"
    different_canonical = _canonical_manifest_bytes(a["id"], "rev-1", [_item("ev-other", "T3", "photo", data, "image/jpeg")], {"T3": len(data)}, len(data))
    different_envelope = _sign_envelope(other_priv, other_pub_b64, different_canonical)

    opened = _open(client, token, a["id"], target="manifest", revision_id="rev-1", claimed_size_bytes=len(different_envelope))
    assert opened.status_code == 201
    session_id = opened.json()["id"]
    client.put(f"/uploads/{session_id}/chunks/0", content=different_envelope, headers={WT_HEADER: token})
    sha = hashlib.sha256(different_envelope).hexdigest()
    complete = client.post(f"/uploads/{session_id}/complete", json={"client_sha256": sha}, headers={WT_HEADER: token})
    assert complete.status_code == 409
    assert "different manifest already exists" in complete.text.lower()


def test_manifest_identical_retry_is_idempotent(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    priv, pub_b64 = _gen_keypair()
    data = b"x" * 10
    canonical = _canonical_manifest_bytes(a["id"], "rev-1", [_item("e1", "T1", "photo", data, "image/jpeg")], {"T1": len(data)}, len(data))
    envelope = _sign_envelope(priv, pub_b64, canonical)

    _, first = _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id="rev-1")
    assert first.status_code == 200
    first_manifest_id = first.json()["manifest_id"]

    # A brand-new session (simulating "app restarted, lost the old session
    # id, opened a fresh one") uploading the EXACT same envelope bytes.
    _, second = _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id="rev-1")
    assert second.status_code == 200, second.text
    assert second.json()["manifest_id"] == first_manifest_id


# ---- evidence-vs-manifest cross-check ----

def test_evidence_upload_before_any_manifest_is_rejected(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    opened = _open(
        client, token, a["id"], target="evidence", task_code="T1", kind="photo", mime="image/jpeg",
        revision_id="rev-1", client_evidence_id="ev-1", claimed_size_bytes=10,
    )
    assert opened.status_code == 409
    assert "manifest" in opened.text.lower()


def test_evidence_with_wrong_bytes_vs_declared_hash_is_rejected_and_not_stored(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    priv, pub_b64 = _gen_keypair()
    declared_bytes = b"the real evidence bytes" * 20
    wrong_bytes = b"a substituted, different file" * 20
    items = [_item("ev-1", "T1", "photo", declared_bytes, "image/jpeg")]
    canonical = _canonical_manifest_bytes(a["id"], "rev-1", items, {"T1": len(declared_bytes)}, len(declared_bytes))
    envelope = _sign_envelope(priv, pub_b64, canonical)
    _, mcomplete = _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id="rev-1")
    assert mcomplete.status_code == 200

    _, ecomplete = _upload_and_complete(
        client, token, a["id"], wrong_bytes, target="evidence", task_code="T1", kind="photo", mime="image/jpeg",
        revision_id="rev-1", client_evidence_id="ev-1",
    )
    assert ecomplete.status_code == 409
    assert "manifest" in ecomplete.text.lower()

    detail = client.get(f"/assessments/{a['id']}", headers={WT_HEADER: token}).json()
    t1 = next(t for t in detail["tasks"] if t["task_code"] == "T1")
    assert t1["evidence"] == [], "a rejected upload must never create an EvidenceItem"

    status = client.get(f"/assessments/{a['id']}/sync-status", headers={WT_HEADER: token}).json()
    item = next(i for i in status["items"] if i["client_evidence_id"] == "ev-1")
    assert item["state"] != "verified"
    assert item["rejection_reason"]


def test_evidence_uploaded_under_wrong_task_binding_is_rejected(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    priv, pub_b64 = _gen_keypair()
    data = b"same bytes, wrong task" * 20
    # Manifest declares this evidenceId as belonging to T1...
    items = [_item("ev-1", "T1", "photo", data, "image/jpeg")]
    canonical = _canonical_manifest_bytes(a["id"], "rev-1", items, {"T1": len(data)}, len(data))
    envelope = _sign_envelope(priv, pub_b64, canonical)
    _, mcomplete = _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id="rev-1")
    assert mcomplete.status_code == 200

    # ...but the phone (bug or tamper) opens the evidence session under T2 instead.
    _, ecomplete = _upload_and_complete(
        client, token, a["id"], data, target="evidence", task_code="T2", kind="photo", mime="image/jpeg",
        revision_id="rev-1", client_evidence_id="ev-1",
    )
    assert ecomplete.status_code == 409
    assert "task binding" in ecomplete.text.lower()


def test_evidence_id_not_declared_in_manifest_is_rejected(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    priv, pub_b64 = _gen_keypair()
    data = b"legit bytes" * 20
    items = [_item("ev-declared", "T1", "photo", data, "image/jpeg")]
    canonical = _canonical_manifest_bytes(a["id"], "rev-1", items, {"T1": len(data)}, len(data))
    envelope = _sign_envelope(priv, pub_b64, canonical)
    _, mcomplete = _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id="rev-1")
    assert mcomplete.status_code == 200

    _, ecomplete = _upload_and_complete(
        client, token, a["id"], data, target="evidence", task_code="T1", kind="photo", mime="image/jpeg",
        revision_id="rev-1", client_evidence_id="ev-NEVER-DECLARED",
    )
    assert ecomplete.status_code == 409
    assert "not declared" in ecomplete.text.lower()


# ---- TOFU device-key pinning ----

def test_second_revision_signed_by_a_different_device_key_is_rejected(client, imported_pack, worker):
    a, token, priv1, pub1_b64, _ = _seal_and_sync_full_package(client, imported_pack, worker, revision_id="rev-1")

    priv2, pub2_b64 = _gen_keypair()
    data = b"a second revision, different device key" * 10
    items = [_item("ev-new", "T3", "photo", data, "image/jpeg")]
    canonical = _canonical_manifest_bytes(a["id"], "rev-2", items, {"T3": len(data)}, len(data))
    envelope = _sign_envelope(priv2, pub2_b64, canonical)

    _, complete = _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id="rev-2")
    assert complete.status_code == 409
    assert "pinned device key" in complete.text.lower()


# ---- revision supersession ----

def test_newer_revision_supersedes_an_unfinished_older_one(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    priv, pub_b64 = _gen_keypair()

    old_data = b"old revision item, abandoned mid-sync" * 20
    old_items = [_item("ev-old", "T1", "photo", old_data, "image/jpeg")]
    old_canonical = _canonical_manifest_bytes(a["id"], "rev-OLD", old_items, {"T1": len(old_data)}, len(old_data))
    old_envelope = _sign_envelope(priv, pub_b64, old_canonical)
    _, old_manifest_complete = _upload_and_complete(client, token, a["id"], old_envelope, target="manifest", revision_id="rev-OLD")
    assert old_manifest_complete.status_code == 200

    # The worker starts (but never finishes) uploading the old revision's
    # one evidence item -- this session stays genuinely "open" across the
    # supersession below, mirroring a real interrupted-then-abandoned sync.
    old_item_session = _open(
        client, token, a["id"], target="evidence", task_code="T1", kind="photo", mime="image/jpeg",
        revision_id="rev-OLD", client_evidence_id="ev-old", claimed_size_bytes=len(old_data),
    )
    assert old_item_session.status_code == 201
    old_session_id = old_item_session.json()["id"]

    # The worker discards/reopens and reseals on-device -- a fresh
    # revisionId, same device key (same real-world scenario the Android
    # SealOrchestrator.discardAndReopen produces).
    new_data = b"new revision item, this is the real one" * 20
    new_items = [_item("ev-new", "T1", "photo", new_data, "image/jpeg")]
    new_canonical = _canonical_manifest_bytes(a["id"], "rev-NEW", new_items, {"T1": len(new_data)}, len(new_data))
    new_envelope = _sign_envelope(priv, pub_b64, new_canonical)
    _, new_manifest_complete = _upload_and_complete(client, token, a["id"], new_envelope, target="manifest", revision_id="rev-NEW")
    assert new_manifest_complete.status_code == 200

    detail = client.get(f"/assessments/{a['id']}", headers={WT_HEADER: token}).json()
    assert detail["current_revision_id"] == "rev-NEW"

    old_status = client.get(
        f"/assessments/{a['id']}/sync-status", params={"revision_id": "rev-OLD"}, headers={WT_HEADER: token},
    ).json()
    assert old_status["manifest_state"] == "none"  # "received" flipped to "superseded", filtered out of the visible set

    # The old revision's already-open evidence session must be rejected on
    # its next mutation -- it must never be allowed to keep uploading or to
    # silently succeed into the wrong (old) revision's evidence set.
    chunk = client.put(f"/uploads/{old_session_id}/chunks/0", content=old_data, headers={WT_HEADER: token})
    assert chunk.status_code == 409
    assert "superseded" in chunk.text.lower()

    # A fresh attempt to open a NEW session for the old, now-invalid
    # revision is independently rejected too (its manifest no longer
    # qualifies as received/verified).
    reopen_attempt = _open(
        client, token, a["id"], target="evidence", task_code="T1", kind="photo", mime="image/jpeg",
        revision_id="rev-OLD", client_evidence_id="ev-old-2", claimed_size_bytes=len(old_data),
    )
    assert reopen_attempt.status_code == 409


# ---- begin/recover idempotent session opening ----

def test_opening_a_session_twice_for_the_same_item_recovers_the_existing_one(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    first = _open(
        client, token, a["id"], target="evidence", task_code="T1", kind="photo", mime="image/jpeg",
        claimed_size_bytes=100,
    )
    # The direct (pre-P6) path never sets revision_id, so recovery doesn't
    # apply there -- re-open WITH a revision_id/client_evidence_id instead,
    # after first seeding a manifest that declares it.
    priv, pub_b64 = _gen_keypair()
    items = [_item("ev-1", "T1", "photo", b"x" * 100, "image/jpeg")]
    canonical = _canonical_manifest_bytes(a["id"], "rev-1", items, {"T1": 100}, 100)
    envelope = _sign_envelope(priv, pub_b64, canonical)
    _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id="rev-1")

    opened_a = _open(
        client, token, a["id"], target="evidence", task_code="T1", kind="photo", mime="image/jpeg",
        revision_id="rev-1", client_evidence_id="ev-1", claimed_size_bytes=100,
    )
    assert opened_a.status_code == 201
    opened_b = _open(
        client, token, a["id"], target="evidence", task_code="T1", kind="photo", mime="image/jpeg",
        revision_id="rev-1", client_evidence_id="ev-1", claimed_size_bytes=100,
    )
    assert opened_b.status_code == 201
    assert opened_a.json()["id"] == opened_b.json()["id"], "a second open for the same item must recover the existing session, not duplicate it"


def _fail_without_postgres(db_session):
    if db_session.bind.dialect.name != "postgresql":
        pytest.fail(
            "this test requires TEST_DATABASE_URL to point at a real PostgreSQL database -- "
            "SQLite has no row-level locking, so the SELECT FOR UPDATE guarantee cannot be "
            "demonstrated against it. See server/README.md for how to run against the "
            "dockerized Postgres."
        )


def test_concurrent_recover_opens_for_the_same_item_never_create_two_sessions(client, db_session, imported_pack, worker):
    """Real two-thread, two-connection proof that the P6 'begin or recover'
    lookup in open_upload_session is race-free: two simultaneous POSTs for
    the exact same (revision, client_evidence_id) must both resolve to the
    SAME session id, never two independent ones racing to upload the same
    logical item twice."""
    _fail_without_postgres(db_session)
    from server.app import schemas
    from server.app.routers import uploads as uploads_router

    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    priv, pub_b64 = _gen_keypair()
    items = [_item("ev-1", "T1", "photo", b"x" * 100, "image/jpeg")]
    canonical = _canonical_manifest_bytes(a["id"], "rev-1", items, {"T1": 100}, 100)
    envelope = _sign_envelope(priv, pub_b64, canonical)
    _upload_and_complete(client, token, a["id"], envelope, target="manifest", revision_id="rev-1")

    url = db_session.bind.url.render_as_string(hide_password=False)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine_a = create_engine(url)
    engine_b = create_engine(url)
    SessionA, SessionB = sessionmaker(bind=engine_a), sessionmaker(bind=engine_b)

    results = {}
    barrier = threading.Barrier(2)

    def _recover(session_factory, key):
        barrier.wait()
        s = session_factory()
        try:
            body = schemas.UploadSessionCreate(
                assessment_id=a["id"], target="evidence", task_code="T1", kind="photo", mime="image/jpeg",
                claimed_size_bytes=100, revision_id="rev-1", client_evidence_id="ev-1",
            )
            out = uploads_router.open_upload_session(body=body, x_worker_token=token, db=s)
            results[key] = ("ok", out.id)
        except HTTPException as e:
            results[key] = ("error", e.status_code)
        finally:
            s.close()

    t_a = threading.Thread(target=_recover, args=(SessionA, "a"))
    t_b = threading.Thread(target=_recover, args=(SessionB, "b"))
    t_a.start()
    t_b.start()
    t_a.join(timeout=30)
    t_b.join(timeout=30)
    engine_a.dispose()
    engine_b.dispose()

    assert results["a"][0] == "ok" and results["b"][0] == "ok", results
    assert results["a"][1] == results["b"][1], f"expected the same recovered session id, got {results}"


# ---- metadata extraction job ----

def test_extract_metadata_job_reads_real_dimensions_and_duration(client, imported_pack, worker, tmp_path, monkeypatch):
    import subprocess

    from server.app import models, worker as worker_module
    from server.app.routers import uploads as uploads_router
    from server.app.worker import _extract_metadata

    # The `client` fixture points uploads_router._storage at its OWN
    # isolated tmp_path (see conftest.py) -- the worker job builds a
    # separate LocalDiskStorage from settings.evidence_dir (exactly like
    # production: api and worker are different processes sharing one
    # volume), so point that at the SAME root the upload actually landed in.
    monkeypatch.setattr(worker_module.settings, "evidence_dir", uploads_router._storage.root)

    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    video_path = tmp_path / "tiny.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=5",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
            "-c:v", "libx264", "-c:a", "aac", "-shortest", str(video_path),
        ],
        capture_output=True, timeout=30, check=True,
    )
    video_bytes = video_path.read_bytes()

    opened, complete = _upload_and_complete(
        client, token, a["id"], video_bytes, target="evidence", task_code="T2", kind="video", mime="video/mp4",
    )
    assert complete.status_code == 200, complete.text
    evidence_id = complete.json()["evidence_id"]

    db = db_session_for_client(client)
    job = models.Job(type="extract_metadata", payload={"evidence_item_id": evidence_id}, max_attempts=3)
    db.add(job)
    db.commit()
    _extract_metadata(db, job)
    db.commit()

    evidence = db.get(models.EvidenceItem, evidence_id)
    assert evidence.metadata_status == "completed"
    assert evidence.width_px == 320
    assert evidence.height_px == 240
    assert evidence.duration_ms is not None and 900 <= evidence.duration_ms <= 1100


def test_extract_metadata_job_degrades_gracefully_when_ffprobe_is_missing(client, imported_pack, worker, monkeypatch):
    from server.app import models, worker as worker_module
    from server.app.routers import uploads as uploads_router

    monkeypatch.setattr(worker_module.settings, "evidence_dir", uploads_router._storage.root)

    a = _new_assessment(client, imported_pack, worker)
    token = a["worker_token"]
    data = b"not really a video" * 10
    opened, complete = _upload_and_complete(
        client, token, a["id"], data, target="evidence", task_code="T2", kind="video", mime="video/mp4",
    )
    assert complete.status_code == 200
    evidence_id = complete.json()["evidence_id"]

    def _raise_not_found(*args, **kwargs):
        raise FileNotFoundError("ffprobe not installed")

    monkeypatch.setattr(worker_module.subprocess, "run", _raise_not_found)

    db = db_session_for_client(client)
    job = models.Job(type="extract_metadata", payload={"evidence_item_id": evidence_id}, max_attempts=3)
    db.add(job)
    db.commit()
    worker_module._extract_metadata(db, job)  # must not raise
    db.commit()

    evidence = db.get(models.EvidenceItem, evidence_id)
    assert evidence.metadata_status == "unavailable"


def db_session_for_client(client):
    """The `client` fixture overrides get_db with a closure over db_session
    but doesn't expose it directly -- reach it via FastAPI's own dependency
    override map, the same object every route handler in this test actually used."""
    from server.app.db import get_db
    from server.app.main import app

    override = app.dependency_overrides[get_db]
    return next(override())


# ---- audit log ----

def test_sync_actions_are_recorded_in_the_audit_log(client, imported_pack, worker):
    a, token, priv, pub_b64, _ = _seal_and_sync_full_package(client, imported_pack, worker, revision_id="rev-1")
    db = db_session_for_client(client)
    from server.app import models

    actions = [row.action for row in db.query(models.AuditLog).filter_by(assessment_id=a["id"]).order_by(models.AuditLog.id)]
    assert "manifest_received" in actions
    assert "sync_package_complete" in actions


# ---- authorisation scoping (reuses the existing cross-assessment pattern) ----

def test_sync_status_requires_worker_token_or_assessor_auth(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    r = client.get(f"/assessments/{a['id']}/sync-status")
    assert r.status_code == 401


def test_worker_register_is_idempotent_and_creates_a_usable_worker(client, imported_pack):
    first = client.post("/workers/register", json={"device_worker_id": "KP-ABC12345", "display_name": "Worker One"})
    assert first.status_code == 200, first.text
    worker_id = first.json()["worker_id"]

    second = client.post("/workers/register", json={"device_worker_id": "KP-ABC12345", "display_name": "Worker One"})
    assert second.status_code == 200
    assert second.json()["worker_id"] == worker_id, "the same device_worker_id must always resolve to the same worker_id"

    created = client.post("/assessments", json={"worker_id": worker_id, "pack_id": imported_pack.id})
    assert created.status_code == 201, created.text


def test_worker_register_different_devices_get_different_workers(client):
    a = client.post("/workers/register", json={"device_worker_id": "KP-DEVICE-A", "display_name": "A"})
    b = client.post("/workers/register", json={"device_worker_id": "KP-DEVICE-B", "display_name": "B"})
    assert a.json()["worker_id"] != b.json()["worker_id"]


def test_pack_lookup_by_code_resolves_the_imported_pack(client, imported_pack):
    r = client.get("/packs/by-code", params={"qp_code": imported_pack.qp_code, "qp_version": imported_pack.qp_version})
    assert r.status_code == 200, r.text
    assert r.json()["pack_id"] == imported_pack.id


def test_pack_lookup_by_code_404s_for_an_unknown_pack(client, imported_pack):
    r = client.get("/packs/by-code", params={"qp_code": "CON/N9999", "qp_version": "v9.9"})
    assert r.status_code == 404


def test_concurrent_registration_for_the_same_device_never_creates_two_workers(client, db_session):
    """Real two-thread, two-connection proof that a lost-and-retried
    POST /workers/register (e.g. the phone retries after a dropped response to what was
    actually a successful call) never creates a duplicate worker row for the same device."""
    _fail_without_postgres(db_session)
    from server.app.routers import workers as workers_router
    from server.app import schemas

    url = db_session.bind.url.render_as_string(hide_password=False)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine_a = create_engine(url)
    engine_b = create_engine(url)
    SessionA, SessionB = sessionmaker(bind=engine_a), sessionmaker(bind=engine_b)

    results = {}
    barrier = threading.Barrier(2)

    def _register(session_factory, key):
        barrier.wait()
        s = session_factory()
        try:
            out = workers_router.register_worker(
                schemas.WorkerRegisterRequest(device_worker_id="KP-RACE-TEST", display_name="Racer"), db=s,
            )
            results[key] = out.worker_id
        finally:
            s.close()

    t_a = threading.Thread(target=_register, args=(SessionA, "a"))
    t_b = threading.Thread(target=_register, args=(SessionB, "b"))
    t_a.start()
    t_b.start()
    t_a.join(timeout=30)
    t_b.join(timeout=30)
    engine_a.dispose()
    engine_b.dispose()

    assert results["a"] == results["b"], f"expected the same worker_id from both racers, got {results}"


def test_sync_status_rejects_a_different_assessments_worker_token(client, imported_pack, worker):
    a1 = _new_assessment(client, imported_pack, worker)
    a2 = _new_assessment(client, imported_pack, worker)
    r = client.get(f"/assessments/{a1['id']}/sync-status", headers={WT_HEADER: a2["worker_token"]})
    assert r.status_code == 401


# ---- audit log endpoint ----

def test_audit_log_requires_assessor_role_not_worker_token(client, imported_pack, worker):
    a = _new_assessment(client, imported_pack, worker)
    r = client.get(f"/assessments/{a['id']}/audit-log", headers={WT_HEADER: a["worker_token"]})
    assert r.status_code == 401
    r_noauth = client.get(f"/assessments/{a['id']}/audit-log")
    assert r_noauth.status_code == 401


def test_audit_log_records_old_and_new_score_on_rescoring(client, imported_pack, worker, assessor_headers):
    a = _new_assessment(client, imported_pack, worker)
    client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: a["worker_token"]})
    client.post(f"/assessments/{a['id']}/start-review", headers=assessor_headers)
    review = client.get(f"/assessments/{a['id']}/review", headers=assessor_headers).json()
    pc = review[0]["pc_full_id"]

    first = client.put(f"/assessments/{a['id']}/review", headers=assessor_headers, json={
        "pc_full_id": pc, "score_level": 1, "evidence_status": "DEMONSTRATED", "expected_version": 0,
    })
    assert first.status_code == 200
    second = client.put(f"/assessments/{a['id']}/review", headers=assessor_headers, json={
        "pc_full_id": pc, "score_level": 3, "evidence_status": "DEMONSTRATED", "expected_version": 1,
    })
    assert second.status_code == 200

    log = client.get(f"/assessments/{a['id']}/audit-log", headers=assessor_headers)
    assert log.status_code == 200, log.text
    scored_entries = [e for e in log.json() if e["action"] == "scored"]
    assert len(scored_entries) == 2
    assert scored_entries[0]["details"]["old_score_level"] is None
    assert scored_entries[0]["details"]["new_score_level"] == 1
    assert scored_entries[1]["details"]["old_score_level"] == 1
    assert scored_entries[1]["details"]["new_score_level"] == 3
    assert scored_entries[1]["actor_name"]  # resolved from the assessor's display_name, not just an id
