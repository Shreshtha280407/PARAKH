#!/usr/bin/env python3
"""P6 end-to-end smoke test against a running, seeded KaushalPramaan stack (see
infra/docker-compose.yml). Complements tools/docker_e2e_smoke.py (the P2.2 lifecycle,
unchanged) with everything P6 adds: worker self-registration, pack lookup, a REAL
Android-Keystore-shaped signed manifest (ECDSA secp256r1, exactly the envelope
server/app/manifest_verify.py parses), the chunked manifest+evidence upload protocol,
server-side verification gating submit, the sync-status endpoint, the audit log, and that
scoring/review still work on top of a P6-synced package.

Needs `cryptography` on the host running this script (not stdlib-only, unlike
docker_e2e_smoke.py) -- the one real external dependency required to produce a real EC
signature the same way the Android app's Keystore does. See .github/workflows/ci.yml's
docker-compose-smoke-test job for the one extra `pip install` this requires.

Run with the stack already up and seeded:

    python tools/docker_e2e_smoke_p6.py --base-url http://localhost:8000 \\
        --assessor-email assessor.demo@parakh.test --assessor-password ...
"""
import argparse
import base64
import hashlib
import json
import sys
import urllib.error
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


def call(method: str, url: str, token: str | None = None, body: bytes | dict | None = None,
         worker_token: str | None = None, expect: int = 200, raw: bool = False):
    data: bytes | None
    if raw:
        data = body  # type: ignore[assignment]
    else:
        data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None and not raw:
        req.add_header("Content-Type", "application/json")
    elif raw:
        req.add_header("Content-Type", "application/octet-stream")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if worker_token:
        req.add_header("X-Worker-Token", worker_token)
    try:
        with urllib.request.urlopen(req) as resp:
            status, payload = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        status, payload = e.code, e.read()
    if status != expect:
        print(f"FAIL {method} {url} -> {status} (expected {expect}): {payload[:800]!r}", file=sys.stderr)
        sys.exit(1)
    return json.loads(payload) if payload else None


def build_signed_manifest(assessment_id: int, revision_id: str, items: list[dict],
                           task_totals: dict[str, int], total_bytes: int) -> tuple[bytes, bytes]:
    """Returns (envelope_bytes, canonical_bytes) -- mirrors apps/android/core/seal's
    SealManifest/ManifestSigner/SignedManifestPackage exactly enough for
    server/app/manifest_verify.py to accept it as a real device would produce."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_der = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER, format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    manifest = {
        "assessmentId": assessment_id,
        "revisionId": revision_id,
        "idempotencyKey": f"{assessment_id}:{revision_id}",
        "evidence": items,
        "taskTotals": [{"taskId": t, "finalBytes": b} for t, b in task_totals.items()],
        "assessmentFinalBytes": total_bytes,
        "declarationSummary": {"matchResult": "PARTIAL", "overallCoverage": 0.6, "gapTaskCodes": ["T3", "T5"]},
    }
    canonical_bytes = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    signature = private_key.sign(canonical_bytes, ec.ECDSA(hashes.SHA256()))
    envelope = {
        "manifestBase64": base64.b64encode(canonical_bytes).decode(),
        "signatureBase64": base64.b64encode(signature).decode(),
        "algorithm": "SHA256withECDSA",
        "signerKeyId": "smoke-test-key-1",
        "signerPublicKeyBase64": base64.b64encode(public_der).decode(),
    }
    return json.dumps(envelope).encode("utf-8"), canonical_bytes


def upload_and_complete(base: str, worker_token: str, assessment_id: int, data: bytes, **open_fields) -> dict:
    session = call(
        "POST", f"{base}/uploads", worker_token=worker_token, expect=201,
        body={"assessment_id": assessment_id, "claimed_size_bytes": len(data), **open_fields},
    )
    call("PUT", f"{base}/uploads/{session['id']}/chunks/0", worker_token=worker_token, body=data, raw=True)
    sha = hashlib.sha256(data).hexdigest()
    return call("POST", f"{base}/uploads/{session['id']}/complete", worker_token=worker_token, body={"client_sha256": sha})


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--assessor-email", required=True)
    p.add_argument("--assessor-password", required=True)
    args = p.parse_args()
    base = args.base_url

    print("1. login as assessor")
    login = call("POST", f"{base}/auth/login", body={"email": args.assessor_email, "password": args.assessor_password})
    assessor_token = login["access_token"]

    print("2. worker self-registration is idempotent")
    reg1 = call("POST", f"{base}/workers/register", body={"device_worker_id": "KP-SMOKE0001", "display_name": "Smoke Worker"})
    reg2 = call("POST", f"{base}/workers/register", body={"device_worker_id": "KP-SMOKE0001", "display_name": "Smoke Worker"})
    assert reg1["worker_id"] == reg2["worker_id"], "same device_worker_id must resolve to the same worker_id"
    worker_id = reg1["worker_id"]

    print("3. resolve the pinned QP code/version to a server pack_id")
    pack = call("GET", f"{base}/packs/by-code?qp_code=CON%2FQ0602&qp_version=4.0")
    pack_id = pack["pack_id"]

    print("4. create the assessment (draft)")
    created = call("POST", f"{base}/assessments", body={"worker_id": worker_id, "pack_id": pack_id}, expect=201)
    aid, wt = created["id"], created["worker_token"]
    assert created["status"] == "draft"

    print("5. build and upload a real ECDSA-signed manifest (2 items: T1 photo, T2 video)")
    revision_id = "smoke-rev-1"
    t1_bytes = b"P6 smoke test T1 photo evidence bytes" * 200
    t2_bytes = b"P6 smoke test T2 video evidence bytes" * 500
    items = [
        {"evidenceId": "ev-t1", "taskId": "T1", "kind": "photo", "bytes": len(t1_bytes),
         "sha256": hashlib.sha256(t1_bytes).hexdigest(), "mimeType": "image/jpeg", "processing": "SEALED"},
        {"evidenceId": "ev-t2", "taskId": "T2", "kind": "video", "bytes": len(t2_bytes),
         "sha256": hashlib.sha256(t2_bytes).hexdigest(), "mimeType": "video/mp4", "processing": "SEALED"},
    ]
    envelope_bytes, _canonical = build_signed_manifest(
        aid, revision_id, items, {"T1": len(t1_bytes), "T2": len(t2_bytes)}, len(t1_bytes) + len(t2_bytes),
    )
    manifest_receipt = upload_and_complete(base, wt, aid, envelope_bytes, target="manifest", revision_id=revision_id)
    assert manifest_receipt["status"] == "received", manifest_receipt

    print("6. sync-status shows the manifest received, items still pending")
    status = call("GET", f"{base}/assessments/{aid}/sync-status?revision_id={revision_id}", worker_token=wt)
    assert status["manifest_state"] == "received"
    assert all(i["state"] == "pending" for i in status["items"])

    print("7. upload T1 photo evidence, cross-checked against the verified manifest")
    t1_receipt = upload_and_complete(
        base, wt, aid, t1_bytes, target="evidence", task_code="T1", kind="photo", mime="image/jpeg",
        revision_id=revision_id, client_evidence_id="ev-t1",
    )
    assert t1_receipt["sha256"] == hashlib.sha256(t1_bytes).hexdigest()

    print("8. a deliberately WRONG hash for T2 is rejected, local state would be retained (409)")
    bad_session = call("POST", f"{base}/uploads", worker_token=wt, expect=201, body={
        "assessment_id": aid, "target": "evidence", "task_code": "T2", "kind": "video", "mime": "video/mp4",
        "claimed_size_bytes": len(t2_bytes), "revision_id": revision_id, "client_evidence_id": "ev-t2",
    })
    call("PUT", f"{base}/uploads/{bad_session['id']}/chunks/0", worker_token=wt, body=t2_bytes, raw=True)
    call("POST", f"{base}/uploads/{bad_session['id']}/complete", worker_token=wt, expect=409,
         body={"client_sha256": "0" * 64})

    print("9. submit is correctly blocked until every declared item is verified")
    call("POST", f"{base}/assessments/{aid}/submit", worker_token=wt, expect=409)

    print("10. now upload T2 with the CORRECT hash -- the manifest completes")
    t2_receipt = upload_and_complete(
        base, wt, aid, t2_bytes, target="evidence", task_code="T2", kind="video", mime="video/mp4",
        revision_id=revision_id, client_evidence_id="ev-t2",
    )
    assert t2_receipt["sha256"] == hashlib.sha256(t2_bytes).hexdigest()
    status = call("GET", f"{base}/assessments/{aid}/sync-status?revision_id={revision_id}", worker_token=wt)
    assert status["manifest_state"] == "complete" and status["all_items_verified"], status

    print("11. submit now succeeds -- the full package was verified complete")
    submitted = call("POST", f"{base}/assessments/{aid}/submit", worker_token=wt)
    assert submitted["status"] == "submitted"
    assert submitted["declared_match_result"] == "PARTIAL"
    assert submitted["declared_gap_task_codes"] == ["T3", "T5"]

    print("12. the assessment records the device's pinned public key's revision")
    detail = call("GET", f"{base}/assessments/{aid}", worker_token=wt)
    assert detail["current_revision_id"] == revision_id

    print("13. assessor reviews: evidence is protected, playable, and scoreable")
    review_started = call("POST", f"{base}/assessments/{aid}/start-review", token=assessor_token)
    assert review_started["status"] == "in_review"
    content_req = urllib.request.Request(f"{base}/assessments/{aid}/evidence/{t1_receipt['evidence_id']}/content")
    content_req.add_header("X-Worker-Token", wt)
    with urllib.request.urlopen(content_req) as resp:
        assert resp.read() == t1_bytes
    review = call("GET", f"{base}/assessments/{aid}/review", token=assessor_token)
    pc = review[0]["pc_full_id"]
    score = call("PUT", f"{base}/assessments/{aid}/review", token=assessor_token, body={
        "pc_full_id": pc, "score_level": 3, "evidence_status": "DEMONSTRATED", "expected_version": 0,
    })
    assert score["version"] == 1

    print("14. audit log records the sync-specific actions, with old/new score on rescoring")
    rescored = call("PUT", f"{base}/assessments/{aid}/review", token=assessor_token, body={
        "pc_full_id": pc, "score_level": 2, "evidence_status": "DEMONSTRATED", "expected_version": 1,
    })
    assert rescored["version"] == 2
    audit = call("GET", f"{base}/assessments/{aid}/audit-log", token=assessor_token)
    actions = [e["action"] for e in audit]
    for expected in ("created", "manifest_received", "sync_package_complete", "submitted", "review_started", "scored"):
        assert expected in actions, f"expected '{expected}' in audit actions, got {actions}"
    scored_entries = [e for e in audit if e["action"] == "scored"]
    assert scored_entries[-1]["details"]["old_score_level"] == 3
    assert scored_entries[-1]["details"]["new_score_level"] == 2

    print("15. audit log is protected -- a worker token cannot read it")
    worker_audit_req = urllib.request.Request(f"{base}/assessments/{aid}/audit-log")
    worker_audit_req.add_header("X-Worker-Token", wt)
    try:
        urllib.request.urlopen(worker_audit_req)
        print("FAIL: worker token must not be able to read the audit log", file=sys.stderr)
        sys.exit(1)
    except urllib.error.HTTPError as e:
        assert e.code == 401

    print("ALL P6 END-TO-END CHECKS PASSED")


if __name__ == "__main__":
    main()
