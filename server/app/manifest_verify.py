"""P5 sealed-manifest verification: parses the SignedManifestPackage envelope
a P6 sync upload carries (see apps/android/core/seal/.../SealManifest.kt --
`SignedManifestPackage.toJsonBytes()`), verifies its Android-Keystore ECDSA
signature against the embedded public key, and extracts the declared
evidence item list for later per-item cross-checking.

Deliberately does NOT re-serialize/re-derive the canonical manifest bytes --
the signature is verified over the EXACT bytes the phone produced and
uploaded (base64-decoded as-is), never a server-side re-encoding of the same
logical content. This avoids any need for the server to replicate Kotlin's
canonical JSON serialization rules; it only has to treat the manifest as an
opaque signed blob and then read fields out of it for business logic.
"""
import base64
import binascii
import hashlib
import json
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

# Matches apps/android/core/seal/.../ManifestSigner.kt's SIGNATURE_ALGORITHM.
# A manifest declaring any other algorithm name is rejected outright -- this
# server only ever implements verification for the one algorithm P5 signs
# with, never a dynamically-selected algorithm from client input.
EXPECTED_ALGORITHM = "SHA256withECDSA"

# Generous ceiling for the manifest envelope itself (JSON metadata only, no
# media bytes) -- comfortably covers hundreds of evidence item entries while
# still being far below the per-task/total evidence budgets, so a client
# cannot use the "manifest" upload target to smuggle large payloads through
# a path that bypasses quota.check_quota.
MANIFEST_MAX_BYTES = 2 * 1024 * 1024


class ManifestVerificationError(Exception):
    """Raised for any structurally-invalid or cryptographically-unverifiable
    manifest -- the caller always turns this into a 'rejected' DeviceManifest
    row (never a 500), see routers/uploads.py."""


@dataclass
class ParsedManifest:
    # The manifest's own, client-chosen assessment identifier -- a UUID the
    # Android app generates locally at draft-creation time, baked into the
    # manifest's signed bytes during the fully-offline P5 seal step, long
    # before this assessment is ever bootstrapped on the server (which
    # assigns its own, unrelated integer primary key). The two identifier
    # spaces are never expected to be equal; see Assessment.client_assessment_id
    # in models.py for how the server pins (TOFU) this value instead.
    manifest_assessment_id: str
    revision_id: str
    idempotency_key: str
    canonical_bytes: bytes
    sha256_hex: str
    signature_b64: str
    algorithm: str
    signer_key_id: str
    signer_public_key_b64: str
    items: list[dict]  # [{evidence_id, task_code, kind, bytes, sha256, mime, processing}, ...]
    task_totals: dict[str, int]  # task_code -> declared final bytes
    assessment_total_bytes: int
    declared_match_result: str | None
    declared_coverage_fraction: float | None
    declared_gap_task_codes: list[str] | None
    # P7: the matcher's overall "why" explanation (a flat list of reason
    # strings -- MatchOutput.because on the Android side has no per-task
    # breakdown, so this never invents one). None (not []) when the client
    # never supplied this key at all (pre-P7 Android build), so the report
    # can distinguish "matcher gave no reasons" from "this was never
    # recorded at all".
    declared_match_reasons: list[str] | None


def _b64decode(value: object, field: str) -> bytes:
    if not isinstance(value, str):
        raise ManifestVerificationError(f"envelope field '{field}' must be a base64 string")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ManifestVerificationError(f"envelope field '{field}' is not valid base64: {e}") from e


def _load_ec_public_key(public_key_b64: str) -> ec.EllipticCurvePublicKey:
    """The embedded key is the Android Keystore EC public key's X.509
    SubjectPublicKeyInfo DER encoding, base64-wrapped -- exactly what
    `java.security.PublicKey.getEncoded()` returns for a Keystore-backed EC
    key (see ManifestSignerInstrumentedTest, which round-trips this same
    encoding against a real device key)."""
    der = _b64decode(public_key_b64, "signerPublicKeyBase64")
    try:
        key = serialization.load_der_public_key(der)
    except (ValueError, TypeError) as e:
        raise ManifestVerificationError(f"signerPublicKeyBase64 is not a valid DER public key: {e}") from e
    if not isinstance(key, ec.EllipticCurvePublicKey):
        raise ManifestVerificationError("signerPublicKeyBase64 is not an EC public key")
    return key


def parse_and_verify_envelope(envelope_bytes: bytes, expected_revision_id: str) -> ParsedManifest:
    """Parse a SignedManifestPackage JSON envelope, verify its ECDSA
    signature, then parse the canonical manifest bytes it wraps. Raises
    ManifestVerificationError on any failure -- the caller is responsible
    for recording that as a 'rejected' DeviceManifest, not for crashing the
    request (a malformed/tampered manifest is an expected, handled input,
    not a server bug).

    Deliberately does not take the server's integer assessment id -- the
    manifest's own assessmentId field lives in a different, client-chosen
    identifier space (see ParsedManifest.manifest_assessment_id) and the
    caller is responsible for TOFU-pinning/comparing it, not this parser."""
    if len(envelope_bytes) > MANIFEST_MAX_BYTES:
        raise ManifestVerificationError(f"manifest envelope exceeds the {MANIFEST_MAX_BYTES}-byte ceiling")
    try:
        envelope = json.loads(envelope_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ManifestVerificationError(f"manifest envelope is not valid UTF-8 JSON: {e}") from e
    if not isinstance(envelope, dict):
        raise ManifestVerificationError("manifest envelope must be a JSON object")

    for field in ("manifestBase64", "signatureBase64", "algorithm", "signerKeyId", "signerPublicKeyBase64"):
        if field not in envelope:
            raise ManifestVerificationError(f"manifest envelope missing required field '{field}'")

    algorithm = envelope["algorithm"]
    if algorithm != EXPECTED_ALGORITHM:
        raise ManifestVerificationError(f"unsupported signature algorithm '{algorithm}' (expected '{EXPECTED_ALGORITHM}')")

    canonical_bytes = _b64decode(envelope["manifestBase64"], "manifestBase64")
    signature_bytes = _b64decode(envelope["signatureBase64"], "signatureBase64")
    public_key = _load_ec_public_key(envelope["signerPublicKeyBase64"])

    try:
        public_key.verify(signature_bytes, canonical_bytes, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as e:
        raise ManifestVerificationError("ECDSA signature does not verify against the embedded public key") from e

    sha256_hex = hashlib.sha256(canonical_bytes).hexdigest()

    try:
        manifest = json.loads(canonical_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ManifestVerificationError(f"signed manifest bytes are not valid UTF-8 JSON: {e}") from e
    if not isinstance(manifest, dict):
        raise ManifestVerificationError("signed manifest must be a JSON object")

    for field in ("assessmentId", "revisionId", "idempotencyKey", "evidence", "taskTotals", "assessmentFinalBytes"):
        if field not in manifest:
            raise ManifestVerificationError(f"signed manifest missing required field '{field}'")

    manifest_assessment_id = str(manifest["assessmentId"])
    revision_id = manifest["revisionId"]
    if revision_id != expected_revision_id:
        raise ManifestVerificationError(
            f"manifest revisionId '{revision_id}' does not match the upload session's revision '{expected_revision_id}'"
        )
    idempotency_key = manifest["idempotencyKey"]
    expected_key = f"{manifest_assessment_id}:{expected_revision_id}"
    if idempotency_key != expected_key:
        raise ManifestVerificationError(
            f"manifest idempotencyKey '{idempotency_key}' does not match the expected '{expected_key}'"
        )

    items: list[dict] = []
    for raw in manifest["evidence"]:
        for field in ("evidenceId", "taskId", "kind", "bytes", "sha256"):
            if field not in raw:
                raise ManifestVerificationError(f"manifest evidence entry missing required field '{field}'")
        captured_at_millis = raw.get("capturedAtMillis")
        items.append({
            "evidence_id": str(raw["evidenceId"]),
            "task_code": str(raw["taskId"]),
            "kind": str(raw["kind"]).lower(),
            "bytes": int(raw["bytes"]),
            "sha256": str(raw["sha256"]).lower(),
            "mime": raw.get("mimeType"),
            "processing": raw.get("processing"),
            # Device-reported, NOT independently verified -- see
            # EvidenceItem.device_captured_at's docstring in models.py.
            "captured_at_millis": int(captured_at_millis) if isinstance(captured_at_millis, (int, float)) else None,
        })

    task_totals = {
        str(t["taskId"]): int(t["finalBytes"])
        for t in manifest["taskTotals"]
        if "taskId" in t and "finalBytes" in t
    }

    declaration = manifest.get("declarationSummary") or {}
    gap_codes = declaration.get("gapTaskCodes")
    # The matcher's own overall "why" explanation (MatchOutput.because on the
    # Android side -- a flat list of reason strings for the WHOLE match
    # decision, not scoped per task; the matcher does not produce a
    # structured per-task reason, so this never fabricates one either).
    match_reasons = declaration.get("matchReasons")
    parsed_match_reasons = (
        [str(r) for r in match_reasons] if isinstance(match_reasons, list) else None
    )

    return ParsedManifest(
        manifest_assessment_id=manifest_assessment_id,
        revision_id=revision_id,
        idempotency_key=idempotency_key,
        canonical_bytes=canonical_bytes,
        sha256_hex=sha256_hex,
        signature_b64=envelope["signatureBase64"],
        algorithm=algorithm,
        signer_key_id=envelope["signerKeyId"],
        signer_public_key_b64=envelope["signerPublicKeyBase64"],
        items=items,
        task_totals=task_totals,
        assessment_total_bytes=int(manifest["assessmentFinalBytes"]),
        declared_match_result=declaration.get("matchResult"),
        declared_coverage_fraction=declaration.get("overallCoverage"),
        declared_gap_task_codes=list(gap_codes) if isinstance(gap_codes, list) else None,
        declared_match_reasons=parsed_match_reasons,
    )
