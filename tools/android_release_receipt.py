#!/usr/bin/env python3
"""Record APK identity, refusing unexpected or debug release certificates."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[1]
apk_dir = root / "apps/android/app/build/outputs/apk/release"
signed = os.environ.get("APK_SIGNING") == "approved-release"
apk = apk_dir / ("app-release.apk" if signed else "app-release-unsigned.apk")
sdk = Path(os.environ["ANDROID_HOME"]) / "build-tools/36.0.0"
certificate = None
if signed:
    result = subprocess.run([str(sdk / "apksigner"), "verify", "--print-certs", str(apk)], text=True, capture_output=True, check=True)
    certificate = re.search(r"certificate SHA-256 digest: ([a-fA-F0-9]+)", result.stdout).group(1).lower()
    expected = os.environ["EXPECTED_CERT_SHA256"].replace(":", "").lower()
    if certificate != expected or "CN=Android Debug" in result.stdout:
        raise SystemExit("APK certificate is not the approved release identity")
metadata = subprocess.run([str(sdk / "aapt"), "dump", "badging", str(apk)], text=True, capture_output=True, check=True).stdout
dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=root, text=True, capture_output=True, check=True).stdout.strip())
receipt = {"source_sha": os.environ["RELEASE_SHA"], "artifact": apk.name, "signing": os.environ["APK_SIGNING"],
    "source_tree_dirty": dirty,
    "certificate_sha256": certificate, "sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
    "version_code": re.search(r"versionCode='([^']+)'", metadata).group(1),
    "version_name": re.search(r"versionName='([^']+)'", metadata).group(1),
    "api": "https://api-production-c626.up.railway.app", "installable": signed}
(root / "android-release-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
