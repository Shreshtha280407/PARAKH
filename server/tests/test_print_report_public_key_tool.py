import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization


@pytest.mark.parametrize("layout", ["checkout", "docker"])
@pytest.mark.parametrize("pem", [False, True])
def test_public_key_export_in_checkout_and_packaged_image(tmp_path, layout, pem):
    """Exercise the real CLI with both deployed module layouts and encodings."""
    tools = tmp_path / "tools"
    tools.mkdir()
    script = tools / "print_report_public_key.py"
    shutil.copyfile(Path(__file__).resolve().parents[2] / "tools" / script.name, script)
    application = tmp_path / "server" / "app" if layout == "checkout" else tmp_path / "app"
    application.mkdir(parents=True)
    (application / "__init__.py").touch()
    if layout == "checkout":
        (application.parent / "__init__.py").touch()
    expected_key = "12" * 32
    (application / "report_signing.py").write_text(f'def public_key_hex(): return "{expected_key}"\n')
    command = [sys.executable, str(script)] + (["--pem"] if pem else [])
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    if pem:
        key = serialization.load_pem_public_key(result.stdout.encode())
        assert key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex() == expected_key
    else:
        assert result.stdout.strip() == expected_key
