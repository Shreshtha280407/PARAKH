"""End-to-end proof that tools/verify_report.py actually works offline
against real downloaded bytes -- the P7 exit test: 'editing one byte of
the PDF makes verify_report.py fail'. Runs the real script as a
subprocess (no network, no running server -- just the files on disk),
exactly as an operator would.
"""
import json
import subprocess
import sys
from pathlib import Path

from server.app import report_signing

WT_HEADER = "X-Worker-Token"
ASSESSOR_PASSWORD = "correct horse battery staple"
REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "tools" / "verify_report.py"


def _signed_assessment(client, imported_pack, worker, assessor_headers):
    a = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    client.post(f"/assessments/{a['id']}/submit", headers={WT_HEADER: a["worker_token"]})
    client.post(f"/assessments/{a['id']}/start-review", headers=assessor_headers)
    items = client.get(f"/assessments/{a['id']}/review", headers=assessor_headers).json()
    for item in items:
        client.put(f"/assessments/{a['id']}/review", json={
            "pc_full_id": item["pc_full_id"], "score_level": 3,
            "evidence_status": "DEMONSTRATED", "expected_version": 0,
        }, headers=assessor_headers)
    client.post(f"/assessments/{a['id']}/sign-off", json={
        "password": ASSESSOR_PASSWORD, "final_recommendation": "RECOMMEND_CERTIFICATION",
    }, headers=assessor_headers)
    return a


def test_verify_report_tool_passes_on_the_original_and_fails_on_a_tampered_copy(
    client, imported_pack, worker, assessor_headers, tmp_path,
):
    a = _signed_assessment(client, imported_pack, worker, assessor_headers)

    pdf_bytes = client.get(f"/assessments/{a['id']}/report", params={"format": "pdf"}, headers=assessor_headers).content
    receipt = client.get(f"/assessments/{a['id']}/report", params={"format": "receipt"}, headers=assessor_headers).json()

    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(pdf_bytes)
    (tmp_path / "report.pdf.receipt.json").write_text(json.dumps(receipt))

    pubkey_path = tmp_path / "report_pub.hex"
    pubkey_path.write_text(report_signing.public_key_hex())

    original = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), str(pdf_path), "--pubkey", str(pubkey_path)],
        capture_output=True, text=True,
    )
    assert original.returncode == 0, original.stdout + original.stderr
    assert "signature OK" in original.stdout

    tampered_path = tmp_path / "report_tampered.pdf"
    tampered_bytes = bytearray(pdf_bytes)
    tampered_bytes[-10] ^= 0xFF
    tampered_path.write_bytes(bytes(tampered_bytes))
    (tmp_path / "report_tampered.pdf.receipt.json").write_text(json.dumps(receipt))

    tampered = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), str(tampered_path), "--pubkey", str(pubkey_path)],
        capture_output=True, text=True,
    )
    assert tampered.returncode == 1
    assert "TAMPERED" in tampered.stderr

    wrong_key_path = tmp_path / "wrong_pub.hex"
    wrong_key_path.write_text("ab" * 32)
    wrong_key_result = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), str(pdf_path), "--pubkey", str(wrong_key_path)],
        capture_output=True, text=True,
    )
    assert wrong_key_result.returncode == 1
    assert "INVALID SIGNATURE" in wrong_key_result.stderr


def test_verify_report_tool_pem_pubkey_also_works(client, imported_pack, worker, assessor_headers, tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    a = _signed_assessment(client, imported_pack, worker, assessor_headers)
    pdf_bytes = client.get(f"/assessments/{a['id']}/report", params={"format": "pdf"}, headers=assessor_headers).content
    receipt = client.get(f"/assessments/{a['id']}/report", params={"format": "receipt"}, headers=assessor_headers).json()

    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(pdf_bytes)
    (tmp_path / "report.pdf.receipt.json").write_text(json.dumps(receipt))

    key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(report_signing.public_key_hex()))
    pem = key.public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo)
    pem_path = tmp_path / "report_pub.pem"
    pem_path.write_bytes(pem)

    result = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), str(pdf_path), "--pubkey", str(pem_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_verify_report_tool_missing_receipt_fails_closed(client, imported_pack, worker, assessor_headers, tmp_path):
    a = _signed_assessment(client, imported_pack, worker, assessor_headers)
    pdf_bytes = client.get(f"/assessments/{a['id']}/report", params={"format": "pdf"}, headers=assessor_headers).content
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(pdf_bytes)  # no receipt saved alongside

    result = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), str(pdf_path), "--pubkey", report_signing.public_key_hex()],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "receipt not found" in result.stderr
