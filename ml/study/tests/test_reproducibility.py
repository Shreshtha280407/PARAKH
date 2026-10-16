import json
import subprocess
import sys

from ml.study.agreement import run
from ml.study.common import HERE, ROOT
from ml.study.generate_demo_data import generate
from ml.study.reproduce import REPORT_FILES, build
from ml.study.simulate_ratings import simulate
from ml.study.validate_dataset import DATA_FILES


def test_byte_identical_generation_and_seed_sensitivity(dataset, tmp_path):
    target = tmp_path / "same"
    generate(target)
    simulate(target / "expected_pc_levels.csv")
    for name in DATA_FILES:
        assert (target / name).read_bytes() == (dataset / name).read_bytes()
    different = tmp_path / "different"
    generate(different, seed=43)
    assert (different / "packages.jsonl").read_bytes() != (dataset / "packages.jsonl").read_bytes()


def test_reproducible_reports_in_different_directories(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    build(first, count=4, bootstrap=12)
    build(second, count=4, bootstrap=12)
    for folder, names in (("data", DATA_FILES), ("reports", REPORT_FILES)):
        for name in names:
            assert (first / folder / name).read_bytes() == (second / folder / name).read_bytes()


def test_cli_reference_legacy_alias_and_outside_cwd(dataset, tmp_path):
    for option in ("--reference", "--gold"):
        out = tmp_path / (option.removeprefix("--") + ".md")
        process = subprocess.run([sys.executable, str(HERE / "agreement.py"), str(dataset / "simulated_ratings.csv"),
                                  option, str(dataset / "expected_pc_levels.csv"), "--bootstrap", "0", "--out", str(out)],
                                 cwd=tmp_path, text=True, capture_output=True)
        assert process.returncode == 0, process.stderr
        assert "not evidence of agreement improvement" in out.read_text()
    assert (tmp_path / "gold.md").read_bytes() == (tmp_path / "reference.md").read_bytes()


def test_cli_validation_failure_has_nonzero_status(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("wrong,header\n1,2\n")
    process = subprocess.run([sys.executable, str(HERE / "agreement.py"), str(bad)], text=True, capture_output=True)
    assert process.returncode == 2
    assert "validation failed" in process.stderr
