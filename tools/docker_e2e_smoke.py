#!/usr/bin/env python3
"""End-to-end smoke test against a running, seeded KaushalPramaan stack
(see infra/docker-compose.yml). Exercises the full P2.2 assessment
lifecycle in one pass: create -> upload evidence -> submit -> login ->
start review -> score -> competency profile -> recommend -> generate
signed report -> public verify -> reassess -> worker token rotate/revoke.

Stdlib only (urllib) -- no new CI dependency for one script. Run with the
stack already up and seeded:

    python tools/docker_e2e_smoke.py --base-url http://localhost:8000 \\
        --assessor-email assessor.demo@parakh.test --assessor-password ...
"""
import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request


def call(method: str, url: str, token: str | None = None, body: dict | None = None,
          worker_token: str | None = None, expect: int = 200):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
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


def put_chunk(base: str, session_id: int, worker_token: str, data: bytes) -> None:
    req = urllib.request.Request(f"{base}/uploads/{session_id}/chunks/0", data=data, method="PUT")
    req.add_header("X-Worker-Token", worker_token)
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200, f"chunk upload failed: {resp.status}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--assessor-email", required=True)
    p.add_argument("--assessor-password", required=True)
    p.add_argument("--worker-id", type=int, default=2)
    p.add_argument("--pack-id", type=int, default=1)
    args = p.parse_args()
    base = args.base_url

    print("1. login as assessor")
    login = call("POST", f"{base}/auth/login", body={"email": args.assessor_email, "password": args.assessor_password})
    token = login["access_token"]

    print("2. create assessment (draft)")
    created = call("POST", f"{base}/assessments", body={"worker_id": args.worker_id, "pack_id": args.pack_id}, expect=201)
    aid, wt = created["id"], created["worker_token"]
    assert created["status"] == "draft"

    print("3. upload evidence to T1, server-verified SHA-256")
    data = b"e2e smoke test evidence bytes, deterministic content for CI"
    sha = hashlib.sha256(data).hexdigest()
    session = call("POST", f"{base}/uploads", worker_token=wt, expect=201, body={
        "assessment_id": aid, "task_code": "T1", "kind": "photo", "mime": "image/jpeg", "claimed_size_bytes": len(data),
    })
    put_chunk(base, session["id"], wt, data)
    receipt = call("POST", f"{base}/uploads/{session['id']}/complete", worker_token=wt, body={"client_sha256": sha})
    assert receipt["sha256"] == sha, "receipt sha256 does not match the uploaded bytes"

    print("4. evidence content is served back byte-for-byte (dual auth: worker token)")
    content_req = urllib.request.Request(f"{base}/assessments/{aid}/evidence/{receipt['evidence_id']}/content")
    content_req.add_header("X-Worker-Token", wt)
    with urllib.request.urlopen(content_req) as resp:
        assert resp.read() == data, "served evidence content does not match what was uploaded"

    print("5. worker submits -- evidence locked after this")
    submitted = call("POST", f"{base}/assessments/{aid}/submit", worker_token=wt)
    assert submitted["status"] == "submitted"
    locked = call("POST", f"{base}/uploads", worker_token=wt, expect=409, body={
        "assessment_id": aid, "task_code": "T2", "kind": "photo", "mime": "image/jpeg", "claimed_size_bytes": 10,
    })

    print("6. assessor starts review")
    review_started = call("POST", f"{base}/assessments/{aid}/start-review", token=token)
    assert review_started["status"] == "in_review"

    print("7. score one performance criterion")
    review = call("GET", f"{base}/assessments/{aid}/review", token=token)
    pc = review[0]["pc_full_id"]
    score = call("PUT", f"{base}/assessments/{aid}/review", token=token, body={
        "pc_full_id": pc, "score_level": 3, "evidence_status": "DEMONSTRATED", "expected_version": 0,
    })
    assert score["version"] == 1

    print("8. competency profile is decision support only")
    profile = call("GET", f"{base}/assessments/{aid}/competency-profile", token=token)
    assert "Decision support only" in profile["disclaimer"]
    assert "final certification/recommendation remains with the human assessor" in profile["disclaimer"]

    print("9. assessor recommends")
    decided = call("POST", f"{base}/assessments/{aid}/decision", token=token, body={
        "decision": "recommended", "notes": "docker e2e smoke test",
    })
    assert decided["status"] == "recommended"

    print("10. generate the signed report")
    report = call("POST", f"{base}/assessments/{aid}/report", token=token, expect=201)
    assert len(report["sha256"]) == 64 and len(report["signature"]) == 128

    print("11. public verify endpoint confirms it, with no auth at all")
    verify = call("GET", f"{base}/reports/{aid}/verify")
    assert verify["valid"] is True

    print("12. reassess is correctly rejected outside needs_reassessment")
    call("POST", f"{base}/assessments/{aid}/reassess", token=token, expect=409)

    print("13. a second assessment routed to needs_reassessment IS reassessable, original untouched")
    created2 = call("POST", f"{base}/assessments", body={"worker_id": args.worker_id, "pack_id": args.pack_id}, expect=201)
    aid2, wt2 = created2["id"], created2["worker_token"]
    call("POST", f"{base}/assessments/{aid2}/submit", worker_token=wt2)
    call("POST", f"{base}/assessments/{aid2}/start-review", token=token)
    call("POST", f"{base}/assessments/{aid2}/decision", token=token, body={"decision": "needs_reassessment"})
    before = call("GET", f"{base}/assessments/{aid2}", token=token)
    reassessed = call("POST", f"{base}/assessments/{aid2}/reassess", token=token, expect=201)
    after = call("GET", f"{base}/assessments/{aid2}", token=token)
    assert reassessed["id"] != aid2 and reassessed["worker_token"] != wt2
    assert before == after, "the original assessment must be untouched by creating its reassessment"
    assert call("GET", f"{base}/assessments/{reassessed['id']}", token=token)["reassessment_of_id"] == aid2

    print("14. worker token rotate invalidates the old one; revoke disables it entirely")
    rotated = call("POST", f"{base}/assessments/{aid}/worker-token/rotate", token=token)
    assert rotated["worker_token"] != wt
    old_rejected = urllib.request.Request(f"{base}/assessments/{aid}", headers={"X-Worker-Token": wt})
    try:
        urllib.request.urlopen(old_rejected)
        print("FAIL: the pre-rotation worker token should no longer work", file=sys.stderr)
        sys.exit(1)
    except urllib.error.HTTPError as e:
        assert e.code == 401
    revoked = call("POST", f"{base}/assessments/{aid}/worker-token/revoke", token=token)
    assert revoked["status"] == "revoked"

    print("ALL P2.2 END-TO-END CHECKS PASSED")


if __name__ == "__main__":
    main()
