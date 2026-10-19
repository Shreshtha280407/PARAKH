import hashlib

import pytest

from server.app.storage import LocalDiskStorage, extension_for_mime, upload_key_for


def test_write_read_delete_round_trip(tmp_path):
    storage = LocalDiskStorage(tmp_path)
    key = upload_key_for(assessment_id=1, task_code="T1", session_id=42)
    data = b"fake jpeg bytes"

    digest = storage.write(key, data)
    assert digest == hashlib.sha256(data).hexdigest()
    assert storage.exists(key)
    assert storage.read(key) == data

    storage.delete(key)
    assert not storage.exists(key)


def test_write_creates_nested_directories(tmp_path):
    storage = LocalDiskStorage(tmp_path)
    key = upload_key_for(assessment_id=7, task_code="T5", session_id=1)
    storage.write(key, b"x")
    assert (tmp_path / "assessments" / "7" / "T5" / "uploads" / "1.part").exists()


def test_path_traversal_is_rejected(tmp_path):
    storage = LocalDiskStorage(tmp_path)
    with pytest.raises(ValueError):
        storage.write("../../etc/passwd", b"nope")
    with pytest.raises(ValueError):
        storage.append("../../etc/passwd", b"nope")


def test_append_builds_up_a_file_across_multiple_calls(tmp_path):
    storage = LocalDiskStorage(tmp_path)
    key = upload_key_for(assessment_id=1, task_code="T1", session_id=1)
    storage.append(key, b"hello ")
    storage.append(key, b"world")
    assert storage.read(key) == b"hello world"
    assert storage.size(key) == 11


def test_size_of_missing_key_is_zero(tmp_path):
    storage = LocalDiskStorage(tmp_path)
    key = upload_key_for(assessment_id=1, task_code="T1", session_id=99)
    assert storage.size(key) == 0


def test_sha256_streams_without_loading_whole_file_api_matches_hashlib(tmp_path):
    storage = LocalDiskStorage(tmp_path)
    key = upload_key_for(assessment_id=1, task_code="T1", session_id=2)
    data = b"streamed content " * 1000
    storage.write(key, data)
    assert storage.sha256(key) == hashlib.sha256(data).hexdigest()


def test_extension_for_mime_covers_the_allow_list():
    assert extension_for_mime("image/jpeg") == ".jpg"
    assert extension_for_mime("image/png") == ".png"
    assert extension_for_mime("image/webp") == ".webp"
    assert extension_for_mime("video/mp4") == ".mp4"
    assert extension_for_mime("video/webm") == ".webm"
    assert extension_for_mime("application/octet-stream") == ".bin"
def test_signed_object_write_once_never_replaces_bytes(tmp_path):
    from server.app.storage import LocalDiskStorage
    import pytest
    storage = LocalDiskStorage(tmp_path)
    storage.write_once('reports/one.pdf', b'original signed PDF')
    with pytest.raises(FileExistsError):
        storage.write_once('reports/one.pdf', b'replacement PDF')
    assert storage.read('reports/one.pdf') == b'original signed PDF'
    assert not list((tmp_path / 'reports').glob('.report-*'))
