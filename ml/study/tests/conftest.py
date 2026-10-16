from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from ml.study.generate_demo_data import generate
from ml.study.simulate_ratings import simulate


@pytest.fixture(scope="session")
def dataset(tmp_path_factory):
    data = tmp_path_factory.mktemp("d3-data")
    generate(data)
    simulate(data / "expected_pc_levels.csv")
    return data
