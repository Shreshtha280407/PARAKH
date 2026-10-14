#!/usr/bin/env python3
"""P6/P7 end-to-end smoke test against a running, seeded KaushalPramaan stack (see
infra/docker-compose.yml). Complements tools/docker_e2e_smoke.py (the P2.2/P7
password-confirmed-sign-off lifecycle over the direct-upload protocol) with everything
P6 adds: worker self-registration, pack lookup, a REAL Android-Keystore-shaped signed
manifest (ECDSA secp256r1, exactly the envelope server/app/manifest_verify.py parses),
the chunked manifest+evidence upload protocol, server-side verification gating submit,
the sync-status endpoint, the audit log, and that scoring/review still work on top of a
P6-synced package -- PLUS the P7 task-specific reassessment loop this protocol enables:
a targeted reassessment request locks every task except the ones reopened, the v2
manifest re-declares an unchanged task's evidence BY REFERENCE (never re-uploaded),
resubmission returns the assessment to the review queue, and the reopened task's PCs
must be re-scored before a password-confirmed sign-off can produce the v2 signed report.

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
                           task_totals: dict[str, int], total_bytes: int, private_key=None,
                           declaration: dict | None = None) -> tuple[bytes, bytes, "ec.EllipticCurvePrivateKey"]:
    """Returns (envelope_bytes, canonical_bytes, private_key) -- mirrors
    apps/android/core/seal's SealManifest/ManifestSigner/SignedManifestPackage
    exactly enough for server/app/manifest_verify.py to accept it as a real
    device would produce. Pass the SAME private_key back in for a later
    revision of the SAME assessment -- a real phone's Android Keystore
    signing key is stable across app restarts/reassessment cycles, and the
    server pins (TOFU) the first manifest's key for the assessment's
    lifetime (Assessment.device_public_key_b64)."""
    if private_key is None:
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
        "declarationSummary": declaration or {"matchResult": "PARTIAL", "overallCoverage": 0.6, "gapTaskCodes": ["T3", "T5"]},
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
    return json.dumps(envelope).encode("utf-8"), canonical_bytes, private_key


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
    envelope_bytes, _canonical, device_key = build_signed_manifest(
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

    print("15b. score every T2 (CON/N0602) PC too, so reopening T2 below has real scores to flag needs_review on")
    review_now = call("GET", f"{base}/assessments/{aid}/review", token=assessor_token)
    for item in review_now:
        if item["pc_full_id"].startswith("CON/N0602."):
            call("PUT", f"{base}/assessments/{aid}/review", token=assessor_token, body={
                "pc_full_id": item["pc_full_id"], "score_level": 3, "evidence_status": "DEMONSTRATED",
                "expected_version": item["score"]["version"] if item["score"] else 0,
            })

    print("15. audit log is protected -- a worker token cannot read it")
    worker_audit_req = urllib.request.Request(f"{base}/assessments/{aid}/audit-log")
    worker_audit_req.add_header("X-Worker-Token", wt)
    try:
        urllib.request.urlopen(worker_audit_req)
        print("FAIL: worker token must not be able to read the audit log", file=sys.stderr)
        sys.exit(1)
    except urllib.error.HTTPError as e:
        assert e.code == 401

    print("16. assessor requests a targeted reassessment of T2 only, with a reason and capture instructions")
    blank_reason = call("POST", f"{base}/assessments/{aid}/reassessment-requests", token=assessor_token, expect=422, body={
        "task_codes": ["T2"], "reason": "   ", "capture_instructions": "retake T2",
    })
    reassessment_request = call("POST", f"{base}/assessments/{aid}/reassessment-requests", token=assessor_token, expect=201, body={
        "task_codes": ["T2"], "reason": "tool use not clearly visible on camera", "capture_instructions": "retake T2 with the tool fully in frame",
    })
    assert reassessment_request["revision_number"] == 2
    detail = call("GET", f"{base}/assessments/{aid}", token=assessor_token)
    assert detail["status"] == "needs_reassessment"

    print("17. T1 (not reopened) is locked; T2 (reopened) accepts a fresh upload session")
    revision_id_v2 = "smoke-rev-2"
    locked = call("POST", f"{base}/uploads", worker_token=wt, expect=409, body={
        "assessment_id": aid, "target": "evidence", "task_code": "T1", "kind": "photo", "mime": "image/jpeg",
        "claimed_size_bytes": 10, "revision_id": revision_id_v2, "client_evidence_id": "ev-t1-sneaky",
    })

    print("18. v2 manifest re-declares T1 by reference (never re-uploaded) + a brand-new T2 item")
    t2_v2_bytes = b"P6 smoke test T2 RETAKEN video evidence bytes" * 500
    items_v2 = [
        {"evidenceId": "ev-t1", "taskId": "T1", "kind": "photo", "bytes": len(t1_bytes),
         "sha256": hashlib.sha256(t1_bytes).hexdigest(), "mimeType": "image/jpeg", "processing": "SEALED"},
        {"evidenceId": "ev-t2-v2", "taskId": "T2", "kind": "video", "bytes": len(t2_v2_bytes),
         "sha256": hashlib.sha256(t2_v2_bytes).hexdigest(), "mimeType": "video/mp4", "processing": "SEALED"},
    ]
    envelope_v2, _canonical_v2, _ = build_signed_manifest(
        aid, revision_id_v2, items_v2, {"T1": len(t1_bytes), "T2": len(t2_v2_bytes)},
        len(t1_bytes) + len(t2_v2_bytes), private_key=device_key,
    )
    manifest_receipt_v2 = upload_and_complete(base, wt, aid, envelope_v2, target="manifest", revision_id=revision_id_v2)
    assert manifest_receipt_v2["status"] == "received", manifest_receipt_v2

    t2_v2_receipt = upload_and_complete(
        base, wt, aid, t2_v2_bytes, target="evidence", task_code="T2", kind="video", mime="video/mp4",
        revision_id=revision_id_v2, client_evidence_id="ev-t2-v2",
    )
    status_v2 = call("GET", f"{base}/assessments/{aid}/sync-status?revision_id={revision_id_v2}", worker_token=wt)
    assert status_v2["manifest_state"] == "complete" and status_v2["all_items_verified"], status_v2
    t1_state = next(i for i in status_v2["items"] if i["client_evidence_id"] == "ev-t1")
    assert t1_state["state"] == "verified"  # satisfied by the ORIGINAL v1 upload -- never re-sent

    print("19. resubmit returns the assessment to 'submitted' and fulfils the reassessment request")
    resubmitted = call("POST", f"{base}/assessments/{aid}/submit", worker_token=wt)
    assert resubmitted["status"] == "submitted"
    requests_after = call("GET", f"{base}/assessments/{aid}/reassessment-requests", token=assessor_token)
    assert requests_after[0]["status"] == "fulfilled"

    print("20. v1's T1 evidence and T1's original score remain exactly as they were (immutable)")
    detail_after = call("GET", f"{base}/assessments/{aid}", token=assessor_token)
    t1_task = next(t for t in detail_after["tasks"] if t["task_code"] == "T1")
    assert len(t1_task["evidence"]) == 1 and t1_task["evidence"][0]["is_current_revision"] is True
    t2_task = next(t for t in detail_after["tasks"] if t["task_code"] == "T2")
    assert len(t2_task["evidence"]) == 2  # old (historical) + new (current)
    assert sum(1 for e in t2_task["evidence"] if e["is_current_revision"]) == 1

    print("21. re-review T2's reopened PC (the T1 PC scored earlier needs no re-review); sign off")
    call("POST", f"{base}/assessments/{aid}/start-review", token=assessor_token)
    review_v2 = call("GET", f"{base}/assessments/{aid}/review", token=assessor_token)
    t2_pcs = [i for i in review_v2 if i["pc_full_id"].startswith("CON/N0602.")]
    assert t2_pcs and all(i["score"]["needs_review"] for i in t2_pcs), "T2's PCs must be flagged needs_review after reopening"
    for i in t2_pcs:
        call("PUT", f"{base}/assessments/{aid}/review", token=assessor_token, body={
            "pc_full_id": i["pc_full_id"], "score_level": 3, "evidence_status": "DEMONSTRATED",
            "expected_version": i["score"]["version"],
        })

    profile_v2 = call("GET", f"{base}/assessments/{aid}/competency-profile", token=assessor_token)
    wrong_pw = call("POST", f"{base}/assessments/{aid}/sign-off", token=assessor_token, expect=401, body={
        "password": "not-the-real-password", "final_recommendation": profile_v2["computed_outcome"],
    })
    signed = call("POST", f"{base}/assessments/{aid}/sign-off", token=assessor_token, expect=201, body={
        "password": args.assessor_password, "final_recommendation": profile_v2["computed_outcome"],
    })
    assert signed["revision_number"] == 2

    print("22. public /verify/{report_id} confirms the v2 report; a tampered local copy fails offline verify")
    verify = call("GET", f"{base}/verify/{signed['report_uid']}")
    assert verify["valid"] is True and verify["revision_number"] == 2

    print("ALL P6/P7 END-TO-END CHECKS PASSED")


if __name__ == "__main__":
    main()
