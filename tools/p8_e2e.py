#!/usr/bin/env python3
"""P8 signed upload/resume/reassessment fixtures against a REAL running API.

All media is freshly generated, privacy-safe synthetic test media. Flags are
explicit contract fixtures, not claimed Android inference or field accuracy.
The output contains only IDs/expectations, never worker or assessor tokens.
"""
import argparse
import base64
import copy
import hashlib
import json
import subprocess
import tempfile
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from docker_e2e_smoke_p6 import call, upload_and_complete

ROOT = Path(__file__).resolve().parents[1]


def signed(assessment_id, revision, items, key):
    totals = {t: sum(i["bytes"] for i in items if i["taskId"] == t) for t in {i["taskId"] for i in items}}
    manifest = {"schemaVersion": 2, "assessmentId": str(assessment_id), "revisionId": revision,
                "idempotencyKey": f"{assessment_id}:{revision}", "evidence": items,
                "taskTotals": [{"taskId": t, "finalBytes": b} for t, b in totals.items()], "assessmentFinalBytes": sum(totals.values())}
    canonical = json.dumps(manifest, separators=(",", ":")).encode()
    pub = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return json.dumps({"manifestBase64": base64.b64encode(canonical).decode(),
                       "signatureBase64": base64.b64encode(key.sign(canonical, ec.ECDSA(hashes.SHA256()))).decode(),
                       "algorithm": "SHA256withECDSA", "signerKeyId": "p8-synthetic-test-key",
                       "signerPublicKeyBase64": base64.b64encode(pub).decode()}).encode()


def item(aid, revision, task, kind, data, *, revision_number=1, status="COMPLETED", legacy=False):
    fixture = json.loads((ROOT / f"contracts/fixtures/assistance-v1-{'video' if kind == 'video' else 'photo'}.json").read_text())
    eid = f"{task}-v{revision_number}-{uuid.uuid4().hex[:12]}"
    digest = hashlib.sha256(data).hexdigest()
    fixture.update(assessmentId=str(aid), taskId=task, evidenceId=eid, revisionId=revision,
                   revisionNumber=revision_number, mediaSha256=digest, status=status)
    if status != "COMPLETED":
        fixture.update(quality=None, hands=None, flags=[], completedAtMillis=None)
    value = {"evidenceId": eid, "taskId": task, "kind": kind, "bytes": len(data), "sha256": digest,
             "mimeType": "video/mp4" if kind == "video" else "image/jpeg", "processing": "FITS_AS_IS"}
    if kind == "video":
        value["durationMillis"] = 5000
    if not legacy:
        value["assistance"] = fixture
    return value


def run(base, email, password, output):
    run_id = "p8-" + uuid.uuid4().hex[:12]
    token = call("POST", f"{base}/auth/login", body={"email": email, "password": password})["access_token"]
    worker = call("POST", f"{base}/workers/register", body={"device_worker_id": run_id, "display_name": "P8 synthetic integration fixture"})
    pack = call("GET", f"{base}/packs/by-code?qp_code=CON%2FQ0602&qp_version=4.0")
    assessment = call("POST", f"{base}/assessments", body={"worker_id": worker["worker_id"], "pack_id": pack["pack_id"]}, expect=201)
    aid, wt = assessment["id"], assessment["worker_token"]
    key = ec.generate_private_key(ec.SECP256R1())
    revision = run_id + "-v1"
    with tempfile.TemporaryDirectory(prefix="parakh-p8-synthetic-") as temp:
        video_path = Path(temp) / "video.mp4"
        photo_path = Path(temp) / "photo.jpg"
        for path, source, args in [
            (video_path, "testsrc2=size=320x240:rate=10", ["-t", "5", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p"]),
            (photo_path, "color=black:size=320x240", ["-frames:v", "1"]),
        ]:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", source, *args, str(path)], check=True)
        video, photo = video_path.read_bytes(), photo_path.read_bytes()
    entries = [item(aid, revision, "T1", "photo", photo), item(aid, revision, "T2", "video", video),
               item(aid, revision, "T3", "photo", photo, status="UNAVAILABLE"),
               item(aid, revision, "T4", "photo", photo, status="QUEUED"), item(aid, revision, "T5", "photo", photo, legacy=True)]
    entries[1]["assistance"]["flags"].insert(1, {"type": "OVEREXPOSED", "startMs": 4999, "endMs": 5000,
        "severity": "review", "observed": None, "threshold": None})  # player boundary fixture, not inference
    receipt = upload_and_complete(base, wt, aid, signed(aid, revision, entries, key), target="manifest", revision_id=revision)
    assert receipt["status"] == "received"
    ids = {}
    for entry in entries:
        payload = video if entry["kind"] == "video" else photo
        opts = dict(target="evidence", task_code=entry["taskId"], kind=entry["kind"], mime=entry["mimeType"],
                    revision_id=revision, client_evidence_id=entry["evidenceId"])
        if entry["kind"] == "video":
            session = call("POST", f"{base}/uploads", worker_token=wt, expect=201,
                           body={"assessment_id": aid, "claimed_size_bytes": len(payload), **opts})
            cut = len(payload) // 2
            ack = call("PUT", f"{base}/uploads/{session['id']}/chunks/0", worker_token=wt, body=payload[:cut], raw=True)
            recovered = call("GET", f"{base}/uploads/{session['id']}", worker_token=wt)
            assert recovered["received_bytes"] == cut and recovered["next_chunk_index"] == 1
            duplicate = call("PUT", f"{base}/uploads/{session['id']}/chunks/0", worker_token=wt, body=payload[:cut], raw=True)
            assert duplicate["received_bytes"] == ack["received_bytes"]
            call("PUT", f"{base}/uploads/{session['id']}/chunks/1", worker_token=wt, body=payload[cut:], raw=True)
            result = call("POST", f"{base}/uploads/{session['id']}/complete", worker_token=wt, body={"client_sha256": entry["sha256"]})
            repeated = call("POST", f"{base}/uploads/{session['id']}/complete", worker_token=wt, body={"client_sha256": entry["sha256"]})
            assert repeated["evidence_id"] == result["evidence_id"]
        else:
            result = upload_and_complete(base, wt, aid, payload, **opts)
        ids[entry["taskId"]] = result["evidence_id"]
    submitted = call("POST", f"{base}/assessments/{aid}/submit", worker_token=wt)
    assert submitted["status"] == "submitted"
    assert all(i["score"] is None for i in call("GET", f"{base}/assessments/{aid}/review", token=token))
    detail = call("GET", f"{base}/assessments/{aid}", token=token)
    assert next(t for t in detail["tasks"] if t["task_code"] == "T2")["evidence"][0]["assistance"] == entries[1]["assistance"]
    call("GET", f"{base}/assessments/{aid}", expect=401)
    call("POST", f"{base}/assessments/{aid}/start-review", token=token)
    call("POST", f"{base}/assessments/{aid}/reassessment-requests", token=token, expect=201,
         body={"task_codes": ["T2"], "reason": "Synthetic P8 revision isolation check", "capture_instructions": "Recapture T2 only"})
    next_revision = run_id + "-v2"
    changed = item(aid, next_revision, "T2", "video", video, revision_number=2)
    changed["assistance"]["flags"] = [{"type": "DARK", "startMs": 2000, "endMs": 3000, "severity": "review", "observed": None, "threshold": None}]
    inherited = [dict(copy.deepcopy(e), processing="INHERITED") for e in entries if e["taskId"] != "T2"]
    receipt = upload_and_complete(base, wt, aid, signed(aid, next_revision, inherited + [changed], key), target="manifest", revision_id=next_revision)
    assert receipt["status"] == "received"
    new_video = upload_and_complete(base, wt, aid, video, target="evidence", task_code="T2", kind="video", mime="video/mp4",
                                    revision_id=next_revision, client_evidence_id=changed["evidenceId"])["evidence_id"]
    call("POST", f"{base}/assessments/{aid}/submit", worker_token=wt)
    detail = call("GET", f"{base}/assessments/{aid}", token=token)
    evidence = {e["id"]: e for t in detail["tasks"] for e in t["evidence"]}
    assert not evidence[ids["T2"]]["is_current_revision"]
    assert evidence[ids["T2"]]["assistance"] == entries[1]["assistance"]
    assert evidence[new_video]["is_current_revision"] and evidence[new_video]["assistance"] == changed["assistance"]
    assert evidence[ids["T1"]]["is_current_revision"] and evidence[ids["T1"]]["assistance"]["revisionNumber"] == 1
    # A signed client duration can differ from actual media. Preserve the signed
    # payload; the real player must suppress out-of-playable-range observations.
    mismatch = call("POST", f"{base}/assessments", body={"worker_id": worker["worker_id"], "pack_id": pack["pack_id"]}, expect=201)
    mid, mwt = mismatch["id"], mismatch["worker_token"]
    mrevision = run_id + "-timing"
    mentry = item(mid, mrevision, "T1", "video", video)
    mentry["durationMillis"] = 6000
    mentry["assistance"].update(durationMs=6000, status="PARTIAL", errorCategory="INCOMPLETE_COVERAGE",
        flags=[{"type": "HANDS_NOT_DETECTED", "startMs": 5000, "endMs": 6000, "severity": "review", "observed": None, "threshold": None}])
    mentry["assistance"]["quality"]["status"] = "PARTIAL"
    mentry["assistance"]["quality"]["coverage"]["requestedSamples"] = 12
    mentry["assistance"]["hands"]["status"] = "PARTIAL"
    mentry["assistance"]["hands"]["coverage"]["requestedSamples"] = 6
    upload_and_complete(base, mwt, mid, signed(mid, mrevision, [mentry], ec.generate_private_key(ec.SECP256R1())), target="manifest", revision_id=mrevision)
    mismatch_receipt = upload_and_complete(base, mwt, mid, video, target="evidence", task_code="T1", kind="video", mime="video/mp4", revision_id=mrevision, client_evidence_id=mentry["evidenceId"])
    call("POST", f"{base}/assessments/{mid}/submit", worker_token=mwt)
    report = {"runId": run_id, "assessmentId": aid, "videoEvidenceId": ids["T2"], "currentVideoEvidenceId": new_video,
              "mismatchedDurationAssessmentId": mid, "mismatchedDurationEvidenceId": mismatch_receipt["evidence_id"],
              "source": "generated synthetic media and contract snapshots, real HTTP/PostgreSQL persistence",
              "physicalDevice": False, "fieldAcceptance": "NOT VERIFIED", "apiWorkflow": "PASS", "resumeAndIdempotency": "PASS",
              "warningsPendingUnavailableSubmit": "PASS", "targetedReassessment": "PASS", "historicalSnapshotIsolation": "PASS",
              "automaticScoresCreated": 0, "expectedMarkers": entries[1]["assistance"]["flags"],
              "canonicalAssistanceOverheadBytes": len(json.dumps(entries, separators=(",", ":")).encode()) - len(json.dumps([{k: v for k, v in e.items() if k != "assistance"} for e in entries], separators=(",", ":")).encode()),
              "manifestEnvelopeBytes": len(signed(aid, revision, entries, key))}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "expectedMarkers"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--assessor-email", required=True)
    parser.add_argument("--assessor-password", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run(args.base_url.rstrip("/"), args.assessor_email, args.assessor_password, args.out)
