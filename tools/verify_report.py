#!/usr/bin/env python3
"""Offline/local verification of a signed KaushalPramaan report PDF -- no
network access, no running server required. See docs/gates/P7.md section 4.

Verifies, independently of the server:
  1. SHA-256(pdf_bytes) matches the receipt's declared pdf_sha256 -- a
     single changed byte anywhere in the PDF fails this outright.
  2. The Ed25519 signature in the receipt verifies against the TRUSTED
     public key you supply (never a key embedded in the receipt/bundle
     itself -- that would let a forged bundle "verify" itself).

Usage:
    python tools/verify_report.py out/report_X.pdf --pubkey keys/report_pub.pem
    python tools/verify_report.py out/report_X.pdf --pubkey a1b2c3...  (raw hex)
    python tools/verify_report.py out/report_X.pdf --receipt out/report_X.receipt.json --pubkey ...

The receipt (pdf_sha256 + signature + key_id) is a DETACHED file, fetched
from the server's protected GET /assessments/{id}/report?format=receipt
endpoint (authenticated -- never the public /verify/{id} endpoint, which
deliberately omits the raw signature) and saved alongside the PDF. If
--receipt is omitted, this looks for "<pdf_path>.receipt.json" next to the
PDF by convention.

Exit code 0 = verified. Exit code 1 = failed (tampered, wrong key, missing
receipt, or any other problem) -- this tool never exits 0 on doubt.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path


def _load_public_key_hex(pubkey_arg: str) -> str:
    """Accepts a raw 64-char hex string, OR a path to a file containing
    either a raw hex string or a PEM-encoded Ed25519 public key."""
    path = Path(pubkey_arg)
    if path.is_file():
        content = path.read_text().strip()
    else:
        content = pubkey_arg.strip()

    if content.startswith("-----BEGIN"):
        from cryptography.hazmat.primitives import serialization

        key = serialization.load_pem_public_key(content.encode())
        raw = key.public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )
        return raw.hex()

    hex_value = content.lower()
    if len(hex_value) != 64 or any(c not in "0123456789abcdef" for c in hex_value):
        print(f"ERROR: --pubkey is neither a PEM file nor a 64-char hex Ed25519 public key: {pubkey_arg!r}", file=sys.stderr)
        sys.exit(1)
    return hex_value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf_path", type=Path, help="Path to the downloaded signed report PDF")
    parser.add_argument("--pubkey", required=True, help="Trusted Ed25519 public key: hex string, or path to a hex/PEM file")
    parser.add_argument("--receipt", type=Path, default=None, help="Path to the detached receipt JSON (default: <pdf_path>.receipt.json)")
    args = parser.parse_args()

    if not args.pdf_path.is_file():
        print(f"ERROR: PDF not found: {args.pdf_path}", file=sys.stderr)
        return 1
    receipt_path = args.receipt or args.pdf_path.with_suffix(args.pdf_path.suffix + ".receipt.json")
    if not receipt_path.is_file():
        print(f"ERROR: receipt not found: {receipt_path} (pass --receipt explicitly if it lives elsewhere)", file=sys.stderr)
        return 1

    try:
        receipt = json.loads(receipt_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: could not read receipt {receipt_path}: {e}", file=sys.stderr)
        return 1
    for field in ("pdf_sha256", "signature", "key_id"):
        if field not in receipt:
            print(f"ERROR: receipt is missing required field '{field}'", file=sys.stderr)
            return 1

    pdf_bytes = args.pdf_path.read_bytes()
    computed_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    if computed_sha256 != receipt["pdf_sha256"].lower():
        print(
            f"TAMPERED: computed SHA-256 {computed_sha256} does not match the receipt's "
            f"{receipt['pdf_sha256']} -- this PDF does not match the signed original.",
            file=sys.stderr,
        )
        return 1

    public_key_hex = _load_public_key_hex(args.pubkey)
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        public_key.verify(bytes.fromhex(receipt["signature"]), bytes.fromhex(computed_sha256))
    except (InvalidSignature, ValueError) as e:
        print(f"INVALID SIGNATURE: {e}", file=sys.stderr)
        return 1

    print(f"signature OK · pdf sha256 matches server record ({computed_sha256})")
    print(f"report_id={receipt.get('report_id', '?')} key_id={receipt['key_id']} signed_at={receipt.get('signed_at', '?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
