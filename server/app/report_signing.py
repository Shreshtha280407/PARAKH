"""Ed25519-signed tamper-evident competency profile reports. See
docs/gates/P7.md section 4. The report is explicitly NOT an official
NCVET/MSDE certificate -- see schemas.COMPETENCY_PROFILE_DISCLAIMER and
routers/reports.py's report content.

P7: signs the RENDERED PDF BYTES, not a JSON snapshot -- the PDF is
rendered once (with no hash/signature field inside it, avoiding a circular
self-reference), hashed, signed, and stored immutably; `sign_pdf` and
`verify_pdf` operate on that digest. `canonical_json` (routers/reports.py)
remains an informational, UNSIGNED snapshot used only for the format=json
download.

Key management: REPORT_SIGNING_PRIVATE_KEY is REQUIRED in every
environment (config.py fails fast if unset, including in development --
this server never silently generates a fresh signing key on process
restart, which would invalidate every previously-signed report).
REPORT_SIGNING_KEY_HISTORY holds retired keys' PUBLIC keys only, so a
report signed before a key rotation stays verifiable under its original
key_id.
"""
import hashlib
import json
import base64
import re

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .config import settings

PDF_METADATA_PREFIX = "PARAKH-REPORT-V1."


def pdf_metadata(snapshot: dict) -> str:
    """Public verification fields inside the signed PDF, without private identity."""
    fields = {key: snapshot[key] for key in (
        "report_uid", "revision_number", "computed_recommendation", "final_recommendation", "signed_at",
    )}
    fields["qp"] = f"{snapshot['qp_code']} v{snapshot['qp_version']}"
    encoded = base64.urlsafe_b64encode(canonical_json(fields).encode()).decode().rstrip("=")
    return PDF_METADATA_PREFIX + encoded


def bound_metadata(pdf_bytes: bytes) -> dict | None:
    """Read only our ASCII-only, PDF Info Subject encoding, after crypto validation.

    Historical PDFs predate this binding and remain verifiable as documents.
    This is deliberately not a parser for arbitrary uploaded PDF documents.
    """
    if PDF_METADATA_PREFIX.encode() not in pdf_bytes:
        return None
    match = re.search(rb"/Subject\s*\(PARAKH-REPORT-V1\.([A-Za-z0-9_-]+)\)", pdf_bytes)
    if not match:
        raise ValueError("invalid report metadata")
    encoded = match.group(1)
    result = json.loads(base64.urlsafe_b64decode(encoded + b"=" * (-len(encoded) % 4)))
    if not isinstance(result, dict):
        raise ValueError("invalid report metadata")
    return result


def canonical_json(data: dict) -> str:
    """Deterministic serialization -- used only for the informational,
    unsigned JSON snapshot (format=json download), not for signing."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def _private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(settings.report_signing_private_key))


def public_key_hex() -> str:
    """The CURRENT signing key's public half, derived from the private key
    -- no separate public-key setting to keep in sync for the active key.
    Retired keys are looked up via public_key_for_key_id instead."""
    from cryptography.hazmat.primitives import serialization

    public_bytes = _private_key().public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return public_bytes.hex()


def public_key_for_key_id(key_id: str) -> str | None:
    """Resolve a (possibly retired) key_id to its hex public key. Returns
    None if key_id is neither the current key nor a known retired one --
    the caller must then treat the report as unverifiable, never as
    verified-by-default."""
    if key_id == settings.report_signing_key_id:
        return public_key_hex()
    return settings.report_signing_key_history_map().get(key_id)


def sign_pdf(pdf_bytes: bytes) -> tuple[str, str, str]:
    """Returns (pdf_sha256_hex, signature_hex, key_id). The PDF bytes
    passed in must already be final -- nothing may modify them after this
    call (see routers/reports.py sign_off: render -> sign_pdf -> store,
    strictly in that order, store happening only once, never re-rendered)."""
    digest = hashlib.sha256(pdf_bytes).digest()
    signature = _private_key().sign(digest)
    return digest.hex(), signature.hex(), settings.report_signing_key_id


def verify_pdf(pdf_bytes: bytes, pdf_sha256_hex: str, signature_hex: str, key_id: str) -> bool:
    """True only if ALL of: the stored hash matches a fresh hash of the
    given PDF bytes, AND the signature verifies against key_id's public
    key (current or retired). A single changed byte anywhere in pdf_bytes
    changes the hash and so fails outright -- this is the actual tamper
    test (verify_report.py and test_reports.py both exercise this)."""
    computed = hashlib.sha256(pdf_bytes).hexdigest()
    if computed != pdf_sha256_hex:
        return False
    public_key_hex_value = public_key_for_key_id(key_id)
    if public_key_hex_value is None:
        return False
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex_value))
        public_key.verify(bytes.fromhex(signature_hex), bytes.fromhex(pdf_sha256_hex))
        return True
    except Exception:
        return False
