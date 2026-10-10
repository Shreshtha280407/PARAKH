"""Ed25519-signed tamper-evident competency profile reports. See
docs/gates/P2_2.md section 4. The report is explicitly NOT an official
NCVET/MSDE certificate -- see schemas.COMPETENCY_PROFILE_DISCLAIMER and
routers/reports.py's report content.

Dev convenience vs. production safety: config.py auto-generates an
ephemeral signing key in development if none is set; outside development
it refuses to start without one (see Settings._report_signing_key_fail_fast).
"""
import hashlib
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .config import settings


def canonical_json(data: dict) -> str:
    """Deterministic serialization: the same logical data always produces
    the exact same bytes, so a hash/signature computed now and re-derived
    later from the same inputs will always match."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def _private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(settings.report_signing_private_key))


def public_key_hex() -> str:
    """Derived from the private key -- no separate public-key setting to
    keep in sync; anyone can compute it, but only the private key can sign."""
    from cryptography.hazmat.primitives import serialization

    public_bytes = _private_key().public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return public_bytes.hex()


def sign_report(data: dict) -> tuple[str, str, str, str]:
    """Returns (canonical_json, sha256_hex, signature_hex, key_id)."""
    payload = canonical_json(data)
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    signature = _private_key().sign(digest)
    return payload, digest.hex(), signature.hex(), settings.report_signing_key_id


def verify(canonical_json_str: str, sha256_hex: str, signature_hex: str) -> bool:
    """True only if ALL of: the hash matches the bytes, AND the signature
    verifies against this server's current public key. A single changed
    byte in canonical_json_str changes the hash and so fails outright."""
    computed = hashlib.sha256(canonical_json_str.encode("utf-8")).digest()
    if computed.hex() != sha256_hex:
        return False
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex()))
        public_key.verify(bytes.fromhex(signature_hex), computed)
        return True
    except Exception:
        return False
