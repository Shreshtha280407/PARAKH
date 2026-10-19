"""S3-compatible evidence storage backend (server/app/storage.py's
S3Storage), the backend a hosted Railway + Neon Object Storage deployment
uses instead of the shared Docker volume.

Runs against moto's in-process S3 implementation rather than a live bucket,
so CI needs no cloud credential. The one real-S3 rule moto does NOT enforce
is multipart's 5 MiB minimum part size -- which is precisely the constraint
that makes a naive part-per-chunk upload fail in production -- so
test_finalize_coalesces_chunks_into_parts_above_the_5mib_floor asserts the
part sizes this code actually submits, instead of trusting the mock to
reject them.
"""
import hashlib

import boto3
import pytest
from moto import mock_aws

from server.app.storage import _MIN_PART_BYTES, S3Storage, upload_key_for

BUCKET = "parakh-evidence-test"
MIB = 1024 * 1024


@pytest.fixture()
def storage():
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield S3Storage(
            bucket=BUCKET, region="us-east-1",
            access_key_id="test", secret_access_key="test",
        )


def _staging_keys(storage, key):
    listing = storage._client.list_objects_v2(Bucket=BUCKET, Prefix=f"{key}.staging/")
    return sorted(o["Key"] for o in listing.get("Contents", []))


def test_write_read_delete_round_trip(storage):
    key = upload_key_for(assessment_id=1, task_code="T1", session_id=42)
    data = b"fake jpeg bytes"

    assert storage.write(key, data) == hashlib.sha256(data).hexdigest()
    assert storage.exists(key)
    assert storage.read(key) == data
    assert storage.size(key) == len(data)

    storage.delete(key)
    assert not storage.exists(key)


def test_size_of_missing_key_is_zero(storage):
    assert storage.size(upload_key_for(1, "T1", 99)) == 0


def test_append_accumulates_without_finalize(storage):
    """Mid-upload, size/sha256/read must already reflect every chunk
    received so far -- routers/uploads.py checks the hash BEFORE anything
    renames or assembles, exactly as it does on local disk."""
    key = upload_key_for(1, "T1", 1)
    storage.append(key, b"hello ")
    storage.append(key, b"world")

    assert storage.read(key) == b"hello world"
    assert storage.size(key) == 11
    assert storage.sha256(key) == hashlib.sha256(b"hello world").hexdigest()
    # Durable per chunk: one discrete object each, in upload order.
    assert len(_staging_keys(storage, key)) == 2


def test_each_chunk_is_durable_immediately_so_a_restart_loses_nothing(storage):
    """An API restart mid-upload must not lose acked chunks. A brand-new
    S3Storage (as a restarted container would build) sees them all."""
    key = upload_key_for(1, "T1", 7)
    storage.append(key, b"a" * MIB)
    storage.append(key, b"b" * MIB)

    reborn = S3Storage(bucket=BUCKET, region="us-east-1",
                       access_key_id="test", secret_access_key="test")
    assert reborn.size(key) == 2 * MIB
    assert reborn.sha256(key) == hashlib.sha256(b"a" * MIB + b"b" * MIB).hexdigest()


def test_finalize_coalesces_chunks_into_parts_above_the_5mib_floor(storage):
    """THE constraint this backend exists to solve: PARAKH streams 1 MiB
    chunks, S3 multipart demands >= 5 MiB for every part but the last. A
    part-per-chunk upload would be rejected by real S3 at completion."""
    key = upload_key_for(1, "T1", 2)
    expected = b""
    for i in range(12):                     # 12 MiB over 12 chunks
        chunk = bytes([i]) * MIB
        storage.append(key, chunk)
        expected += chunk

    submitted = []
    original = storage._client.upload_part

    def spy(**kwargs):
        submitted.append(len(kwargs["Body"]))
        return original(**kwargs)

    storage._client.upload_part = spy
    storage.finalize(key, content_type="video/mp4")

    assert len(submitted) >= 2, "12 MiB must span multiple parts"
    for size in submitted[:-1]:
        assert size >= _MIN_PART_BYTES, f"non-final part of {size}B violates S3's 5 MiB floor"
    assert sum(submitted) == len(expected)

    # One real object, correct bytes, correct MIME, no staging left over.
    assert storage.read(key) == expected
    assert storage.size(key) == len(expected)
    assert storage.sha256(key) == hashlib.sha256(expected).hexdigest()
    assert storage._client.head_object(Bucket=BUCKET, Key=key)["ContentType"] == "video/mp4"
    assert _staging_keys(storage, key) == []


def test_single_chunk_finalize_skips_multipart_entirely(storage):
    """Every photo is one chunk -- a 1-part multipart upload would be both
    wasteful and (under 5 MiB) invalid, so this path is a server-side copy."""
    key = upload_key_for(1, "T1", 3)
    data = b"small photo bytes"
    storage.append(key, data)

    def explode(**kwargs):
        raise AssertionError("multipart must not be used for a single chunk")

    storage._client.create_multipart_upload = explode
    storage.finalize(key, content_type="image/jpeg")

    assert storage.read(key) == data
    assert storage._client.head_object(Bucket=BUCKET, Key=key)["ContentType"] == "image/jpeg"
    assert _staging_keys(storage, key) == []


def test_finalize_is_idempotent_on_a_replayed_complete(storage):
    """complete() is retry-safe by contract; finalize() must be too."""
    key = upload_key_for(1, "T1", 4)
    storage.append(key, b"x" * (6 * MIB))
    storage.append(key, b"y" * MIB)
    storage.finalize(key)
    first = storage.sha256(key)

    storage.finalize(key)
    storage.finalize(key)

    assert storage.sha256(key) == first
    assert storage.size(key) == 7 * MIB
    assert _staging_keys(storage, key) == []


def test_delete_removes_staging_so_an_abandoned_upload_leaves_no_orphans(storage):
    """Expired/abandoned sessions must not accrue billable objects, and the
    defensive pre-upload delete in routers/uploads.py must not leave a
    previous attempt's chunks to be prepended onto a new session's bytes."""
    key = upload_key_for(1, "T1", 5)
    for _ in range(3):
        storage.append(key, b"z" * MIB)
    assert len(_staging_keys(storage, key)) == 3

    storage.delete(key)

    assert _staging_keys(storage, key) == []
    assert not storage.exists(key)
    assert storage.size(key) == 0


def test_a_failed_multipart_leaves_no_half_finished_upload(storage):
    """A terminal failure must abort the multipart upload (no orphaned
    parts billing) while KEEPING the staging objects, so the client can
    still retry complete() and succeed."""
    key = upload_key_for(1, "T1", 6)
    for i in range(12):
        storage.append(key, bytes([i]) * MIB)

    aborted = []
    original_abort = storage._client.abort_multipart_upload
    storage._client.abort_multipart_upload = lambda **kw: (
        aborted.append(kw["UploadId"]), original_abort(**kw))[1]
    storage._client.complete_multipart_upload = lambda **kw: (_ for _ in ()).throw(
        RuntimeError("network died at completion"))

    with pytest.raises(RuntimeError, match="network died"):
        storage.finalize(key)

    assert aborted, "a failed multipart upload must be aborted"
    assert storage._client.list_multipart_uploads(Bucket=BUCKET).get("Uploads", []) == []
    assert len(_staging_keys(storage, key)) == 12, "staging must survive for a retry"


def test_open_stream_serves_inclusive_http_ranges_for_video_seeking(storage):
    key = upload_key_for(1, "T1", 8)
    data = bytes(range(256)) * 40 * 1024      # 10 MiB, non-repeating within each 256B
    storage.append(key, data[: 6 * MIB])
    storage.append(key, data[6 * MIB :])
    storage.finalize(key, content_type="video/mp4")

    assert b"".join(storage.open_stream(key)) == data
    # RFC 7233 ranges are inclusive at both ends.
    assert b"".join(storage.open_stream(key, 10, 19)) == data[10:20]
    assert b"".join(storage.open_stream(key, 5 * MIB, 5 * MIB + 99)) == data[5 * MIB : 5 * MIB + 100]
    assert b"".join(storage.open_stream(key, len(data) - 5)) == data[-5:]


def test_open_stream_ranges_work_before_finalize_too(storage):
    key = upload_key_for(1, "T1", 9)
    data = bytes(range(256)) * 8
    storage.append(key, data[:1000])
    storage.append(key, data[1000:])

    assert b"".join(storage.open_stream(key)) == data
    assert b"".join(storage.open_stream(key, 990, 1010)) == data[990:1011]


def test_local_path_materialises_then_always_cleans_up(storage):
    """ffmpeg/ffprobe need a real path (worker.py). The temp file must be
    removed on the way out even when the caller raises, or Railway's small
    container disk fills up."""
    key = upload_key_for(1, "T1", 10)
    data = b"video bytes" * 5000
    storage.append(key, data)
    storage.finalize(key)

    with storage.local_path(key) as path:
        assert path.read_bytes() == data
        leaked = path
    assert not leaked.exists()

    with pytest.raises(ValueError):
        with storage.local_path(key) as path:
            leaked2 = path
            raise ValueError("ffmpeg blew up")
    assert not leaked2.exists()


def test_corrupted_object_is_caught_by_sha256(storage):
    """The worker's verify_evidence job re-hashes stored bytes; silent
    bucket-side corruption must change the digest."""
    key = upload_key_for(1, "T1", 11)
    storage.append(key, b"original evidence")
    storage.finalize(key)
    good = storage.sha256(key)

    storage._client.put_object(Bucket=BUCKET, Key=key, Body=b"tampered evidence")

    assert storage.sha256(key) != good


def test_missing_object_reports_absent_rather_than_raising(storage):
    key = upload_key_for(1, "T1", 12)
    assert not storage.exists(key)
    assert storage.size(key) == 0
def test_signed_object_conditional_put_prevents_overwrite(storage):
    from botocore.exceptions import ClientError
    import pytest
    storage.write_once('reports/one.pdf', b'original signed PDF')
    with pytest.raises(ClientError) as error:
        storage.write_once('reports/one.pdf', b'replacement PDF')
    assert error.value.response['ResponseMetadata']['HTTPStatusCode'] == 412
    assert storage.read('reports/one.pdf') == b'original signed PDF'
