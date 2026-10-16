#!/usr/bin/env python3
"""Build all D3 artifacts, or compare a temporary full regeneration byte for byte."""
import argparse
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.study.agreement import run
from ml.study.common import HERE
from ml.study.generate_demo_data import generate
from ml.study.simulate_ratings import simulate
from ml.study.validate_dataset import DATA_FILES, validate

REPORT_FILES = ("dataset_validation.md", "synthetic_validation.md", "synthetic_validation.json")


def build(destination, *, seed=42, count=20, bootstrap=2000, policy="baseline"):
    destination = Path(destination)
    data, reports = destination / "data", destination / "reports"
    generate(data, seed=seed, count=count)
    simulate(data / "expected_pc_levels.csv", seed=seed, policy=policy)
    counts = validate(data, out=reports / "dataset_validation.md", check_reproducible=True)
    result = run(data / "simulated_ratings.csv", data / "expected_pc_levels.csv", seed=seed,
                 bootstrap=bootstrap, out=reports / "synthetic_validation.md")
    return counts, result


def check(destination=HERE):
    with tempfile.TemporaryDirectory(prefix="parakh-d3-full-") as directory:
        build(directory)
        for folder, names in (("data", DATA_FILES), ("reports", REPORT_FILES)):
            for name in names:
                path = Path(folder) / name
                if (Path(directory) / path).read_bytes() != (Path(destination) / path).read_bytes():
                    raise ValueError(f"full regeneration differs: {path}")
    return len(DATA_FILES) + len(REPORT_FILES)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify the canonical seed-42 / 20-package / 2000-draw baseline without writing to it")
    parser.add_argument("--out-dir", type=Path, default=HERE)
    args = parser.parse_args()
    if args.check:
        print(f"PASS: {check(args.out_dir)} artifacts byte-identical, including full 2000-draw report")
    else:
        counts, _ = build(args.out_dir)
        print(f"PASS: generated and validated {counts['packages']} synthetic packages")


if __name__ == "__main__":
    main()
