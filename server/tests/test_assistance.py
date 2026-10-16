"""Real signed-upload/HTTP/DB integration plus privacy-safe shared contract fixtures."""
import base64
import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from server.app import models
from server.app.assistance import AssistanceSnapshot, validate_snapshot
from server.app.manifest_verify import ManifestVerificationError, parse_and_verify_envelope
from server.tests.test_sync import _gen_keypair, _sign_envelope, _item, _canonical_manifest_bytes, _new_assessment, _upload_and_complete

ROOT = Path(__file__).resolve().parents[2]


def fixture(name="video"):
    return json.loads((ROOT / f"contracts/fixtures/assistance-v1-{name}.json").read_text())


@pytest.mark.parametrize("name", ["photo", "video", "pending"])
def test_shared_kotlin_python_schema_fixture(name):
    raw = fixture(name)
    Draft202012Validator(json.loads((ROOT / "contracts/flags.schema.json").read_text())).validate(raw)
    assert AssistanceSnapshot.model_validate(raw).model_dump() == raw


@pytest.mark.parametrize("mutate", [
    lambda s: s.update(contractVersion=2),
    lambda s: s.update(contractVersion=True),
    lambda s: s.update(source="SERVER"),
    lambda s: s.update(unbounded={"arbitrary": "claim"}),
    lambda s: s["flags"][0].update(endMs=5001),
    lambda s: s["flags"][0].update(startMs=-1),
    lambda s: s["flags"][0].update(startMs=1000, endMs=1000),
    lambda s: s["flags"][0].update(startMs=0.5),
    lambda s: s["flags"][0].update(severity="reject"),
    lambda s: s["flags"][0].update(observed=float("nan")),
    lambda s: s["flags"][0].update(threshold=float("inf")),
    lambda s: s["hands"].update(visibleRatio=1.1),
    lambda s: s["quality"]["provenance"].update(profileSha256="not-a-hash"),
    lambda s: s["hands"]["provenance"].update(modelSha256=None),
    lambda s: s["quality"]["coverage"].update(analysedSamples=11),
    lambda s: s["quality"]["coverage"].update(coveredDurationMs=5001),
    lambda s: s.update(status="QUEUED"),
    lambda s: s.update(status="FAILED"),
    lambda s: s.update(completedAtMillis=None),
    lambda s: s.update(intervalsTruncated=True),
    lambda s: s.update(flags=s["flags"] * 65),
    lambda s: s["hands"].update(status="UNAVAILABLE"),
])
def test_malformed_payload_is_rejected(mutate):
    raw = fixture()
    mutate(raw)
    with pytest.raises((ValidationError, ValueError)):
        AssistanceSnapshot.model_validate(raw)


def envelope(raw=None, *, version=2, duration=5000):
    raw = raw or fixture()
    item = _item(raw["evidenceId"], raw["taskId"], "video", b"video", "video/mp4")
    item.update(assistance=raw, durationMillis=duration, sha256=raw["mediaSha256"])
    manifest = json.loads(_canonical_manifest_bytes(raw["assessmentId"], raw["revisionId"], [item], {"T1": 5}, 5))
    manifest["schemaVersion"] = version
    priv, pub = _gen_keypair()
    return _sign_envelope(priv, pub, json.dumps(manifest).encode()), manifest, priv, pub


def test_signed_flags_are_verified_and_tampering_invalidates_signature():
    env, manifest, _, _ = envelope()
    assert parse_and_verify_envelope(env, "fixture-revision").items[0]["assistance"] == fixture()
    body = json.loads(env)
    manifest["evidence"][0]["assistance"]["flags"] = []
    body["manifestBase64"] = base64.b64encode(json.dumps(manifest).encode()).decode()
    with pytest.raises(ManifestVerificationError, match="signature"):
        parse_and_verify_envelope(json.dumps(body).encode(), "fixture-revision")


@pytest.mark.parametrize("field,value", [("evidenceId", "other"), ("taskId", "T2"), ("mediaSha256", "c"*64), ("revisionId", "other")])
def test_validly_signed_wrong_binding_is_rejected(field, value):
    env, manifest, priv, pub = envelope()
    manifest["evidence"][0]["assistance"][field] = value
    with pytest.raises(ManifestVerificationError):
        parse_and_verify_envelope(_sign_envelope(priv, pub, json.dumps(manifest).encode()), "fixture-revision")


@pytest.mark.parametrize("version", [0, 3, True, "2"])
def test_unsupported_manifest_version_rejected(version):
    env, _, _, _ = envelope(version=version)
    with pytest.raises(ManifestVerificationError):
        parse_and_verify_envelope(env, "fixture-revision")


def test_legacy_manifest_accepts_missing_assistance_and_rejects_v1_with_assistance():
    env, manifest, priv, pub = envelope(version=1)
    with pytest.raises(ManifestVerificationError):
        parse_and_verify_envelope(env, "fixture-revision")
    del manifest["evidence"][0]["assistance"]
    assert "assistance" not in parse_and_verify_envelope(_sign_envelope(priv, pub, json.dumps(manifest).encode()), "fixture-revision").items[0]


def test_duration_and_oversized_shapes_rejected():
    env, _, _, _ = envelope(duration=4999)
    with pytest.raises(ManifestVerificationError):
        parse_and_verify_envelope(env, "fixture-revision")
    raw = fixture()
    raw["extra"] = "x" * 65536
    with pytest.raises(ValueError, match="ceiling"):
        validate_snapshot(raw, assessment_id="a", revision_id="r", item={})


def test_library_duration_limit_is_not_an_evidence_submission_limit():
    raw = fixture("pending")
    raw.update(durationMs=1_200_001, status="UNAVAILABLE", errorCategory="MODEL_UNAVAILABLE")
    env, _, _, _ = envelope(raw, duration=1_200_001)
    assert parse_and_verify_envelope(env, raw["revisionId"]).items[0]["assistance"]["status"] == "UNAVAILABLE"


def test_field_harness_does_not_convert_calibration_or_incomplete_analysis_into_pass():
    from tools.p8_acceptance import evaluate
    rows = []
    for i in range(20):
        raw = fixture("photo")
        raw["mediaSha256"] = f"{i:064x}"
        if i >= 10:
            raw["flags"] = []
        rows.append({"captureId": str(i), "expected": "bad" if i < 10 else "good", "newUnseen": False,
                     "labelledBeforeAnalysis": True, "productCapture": True, "deviceModel": "synthetic-test",
                     "androidVersion": "test", "runId": "test", "sourceRevision": "test", "assistance": raw})
    report = evaluate(rows)
    assert report["badCaptures"]["correctlyFlagged"] == 10
    assert report["goodCaptures"]["falseWarnings"] == 0
    assert report["badCaptures"]["verdict"] == "NOT VERIFIED"
    for row in rows:
        row["newUnseen"] = True
    assert evaluate(rows)["badCaptures"]["verdict"] == "PASS"
    rows[0]["assistance"].update(status="QUEUED", quality=None, flags=[], completedAtMillis=None)
    assert evaluate(rows)["badCaptures"]["verdict"] == "NOT VERIFIED"


@pytest.mark.parametrize("analysis_status", ["COMPLETED", "QUEUED", "UNAVAILABLE", "FAILED"])
def test_real_signed_upload_persists_flags_and_never_blocks_submit(client, imported_pack, worker, assessor_headers, db_session, analysis_status):
    assessment = _new_assessment(client, imported_pack, worker)
    raw = fixture("photo")
    data = b"privacy-safe evidence bytes"
    raw.update(assessmentId=str(assessment["id"]), mediaSha256=hashlib.sha256(data).hexdigest(), status=analysis_status)
    if analysis_status != "COMPLETED":
        raw.update(quality=None, flags=[], completedAtMillis=None)
    item = _item(raw["evidenceId"], "T1", "photo", data, "image/jpeg")
    item["assistance"] = raw
    canonical = json.loads(_canonical_manifest_bytes(raw["assessmentId"], raw["revisionId"], [item], {"T1": len(data)}, len(data)))
    canonical["schemaVersion"] = 2
    priv, pub = _gen_keypair()
    env = _sign_envelope(priv, pub, json.dumps(canonical).encode())
    _, result = _upload_and_complete(client, assessment["worker_token"], assessment["id"], env, target="manifest", revision_id=raw["revisionId"])
    assert result.status_code == 200, result.text
    _, result = _upload_and_complete(client, assessment["worker_token"], assessment["id"], data, target="evidence", task_code="T1", kind="photo", mime="image/jpeg", revision_id=raw["revisionId"], client_evidence_id=raw["evidenceId"])
    assert result.status_code == 200, result.text
    evidence = db_session.get(models.EvidenceItem, result.json()["evidence_id"])
    assert evidence.assistance == raw
    assert evidence.quality_check_status == analysis_status.lower()
    detail = client.get(f"/assessments/{assessment['id']}", headers=assessor_headers)
    assert detail.status_code == 200
    assert detail.json()["tasks"][0]["evidence"][0]["assistance"] == raw
    assert client.get(f"/assessments/{assessment['id']}").status_code == 401
    other = _new_assessment(client, imported_pack, worker)
    assert client.get(f"/assessments/{assessment['id']}", headers={"X-Worker-Token": other["worker_token"]}).status_code == 401
    assert client.get(f"/assessments/{other['id']}/evidence/{evidence.id}/content", headers=assessor_headers).status_code == 404
    submitted = client.post(f"/assessments/{assessment['id']}/submit", headers={"X-Worker-Token": assessment["worker_token"]})
    assert submitted.status_code == 200, submitted.text
    assert db_session.query(models.AssessmentCriterionScore).count() == 0


def test_additive_backend_migration_preserves_populated_prior_schema(tmp_path, db_session, imported_pack, worker, client):
    """Clone populated previous schema into an isolated SQLite file; execute the real
    Alembic operation there. No ALTER/DROP is run against any existing app database."""
    import importlib.util
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import MetaData, create_engine, select, inspect
    from server.app.db import Base
    assessment = _new_assessment(client, imported_pack, worker)
    _, receipt = _upload_and_complete(client, assessment["worker_token"], assessment["id"], b"legacy migration fixture",
        target="evidence", task_code="T1", kind="photo", mime="image/jpeg")
    assert receipt.status_code == 200
    legacy = MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(legacy)
    legacy.tables["evidence_items"]._columns.remove(legacy.tables["evidence_items"].c.assistance)
    engine = create_engine(f"sqlite:///{tmp_path / 'prior.db'}")
    legacy.create_all(engine)
    with engine.begin() as connection:
        for table in legacy.sorted_tables:
            rows = db_session.execute(select(Base.metadata.tables[table.name])).mappings().all()
            if rows:
                connection.execute(table.insert(), [{k: v for k, v in row.items() if k in table.c} for row in rows])
        before = {t.name: connection.execute(select(t)).mappings().all() for t in legacy.sorted_tables}
        assert len(before["evidence_items"]) == 1
        spec = importlib.util.spec_from_file_location("p8_migration", ROOT / "server/alembic/versions/b89e72c4d010_p8_signed_assistance.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
        assert "assistance" in {c["name"] for c in inspect(connection).get_columns("evidence_items")}
        for table in legacy.sorted_tables:
            assert connection.execute(select(table)).mappings().all() == before[table.name]
    engine.dispose()
