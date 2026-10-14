#!/usr/bin/env python3
"""Print the server's current report-signing Ed25519 PUBLIC key (never the
private key), derived from REPORT_SIGNING_PRIVATE_KEY -- for distributing
to operators who need to run tools/verify_report.py offline.

    python tools/print_report_public_key.py --pem > keys/report_pub.pem
    python tools/print_report_public_key.py            # hex, to stdout

Run with the same environment (.env) the server itself uses, so the
printed key actually matches what it signs with.
"""
import argparse
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

if (root / "server" / "app").is_dir():
    from server.app import report_signing  # noqa: E402
else:
    # The Docker image copies server/app directly to /code/app.
    from app import report_signing  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pem", action="store_true", help="Print PEM-encoded SubjectPublicKeyInfo instead of raw hex")
    args = parser.parse_args()

    if args.pem:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(report_signing.public_key_hex()))
        pem = key.public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        sys.stdout.write(pem.decode())
    else:
        print(report_signing.public_key_hex())
    return 0


if __name__ == "__main__":
    sys.exit(main())
