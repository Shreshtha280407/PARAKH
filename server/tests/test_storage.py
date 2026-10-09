import hashlib

import pytest

from server.app.storage import LocalDiskStorage, key_for


def test_write_read_delete_round_trip(tmp_path):
    storage = LocalDiskStorage(tmp_path)
    key = key_for(assessment_id=1, task_code="T1", evidence_id=42, extension=".jpg")
    data = b"fake jpeg bytes"

    digest = storage.write(key, data)
    assert digest == hashlib.sha256(data).hexdigest()
    assert storage.exists(key)
    assert storage.read(key) == data

    storage.delete(key)
    assert not storage.exists(key)


def test_write_creates_nested_directories(tmp_path):
    storage = LocalDiskStorage(tmp_path)
    key = key_for(assessment_id=7, task_code="T5", evidence_id=1, extension=".mp4")
    storage.write(key, b"x")
    assert (tmp_path / "assessments" / "7" / "T5" / "1.mp4").exists()


def test_path_traversal_is_rejected(tmp_path):
    storage = LocalDiskStorage(tmp_path)
    with pytest.raises(ValueError):
        storage.write("../../etc/passwd", b"nope")
