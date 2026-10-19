"""Private evidence storage interface (master plan p.7: "Private Docker
volume behind a Storage interface ... swap to S3/MinIO later without code
changes elsewhere"). Mounted as a private volume in Docker (infra/docker-
compose.yml) -- never exposed via a public/writable static file route.

Keys are server-generated (see upload_key_for / evidence_key_for); client
filenames are never used as paths, to rule out path traversal and
collisions.
"""
import hashlib
import os
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_READ_CHUNK = 1024 * 1024


class Storage(ABC):
    @abstractmethod
    def write_once(self, key: str, data: bytes) -> str:
        """Atomically create a complete object; fail if the key already exists."""

    @abstractmethod
    def write(self, key: str, data: bytes) -> str:
        """Overwrite key with data, return its sha256 hex digest."""

    @abstractmethod
    def append(self, key: str, data: bytes) -> None:
        """Append data to key, creating it if absent (resumable chunk upload)."""

    @abstractmethod
    def read(self, key: str) -> bytes: ...

    @abstractmethod
    def size(self, key: str) -> int: ...

    @abstractmethod
    def sha256(self, key: str) -> str:
        """Stream the stored object through SHA-256 without loading it
        entirely into memory."""

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def probe(self) -> bool:
        """Round-trip a tiny object to prove the backend is genuinely
        reachable and writable -- what GET /health reports as
        "storage". Must never raise: a dead backend is False, not a 500."""

    def finalize(self, key: str, content_type: str | None = None) -> None:
        """Make `key` a single, directly readable object once a resumable
        upload has received every chunk. A no-op for backends that already
        append in place (local disk); the S3 backend assembles its staged
        per-chunk objects into one object here. Idempotent -- a replayed
        complete() must not corrupt or duplicate anything."""

    @abstractmethod
    @contextmanager
    def local_path(self, key: str) -> Iterator[Path]:
        """Yield a real filesystem path for `key`, for the one thing that
        genuinely cannot take a stream: handing a file to ffmpeg/ffprobe as
        a subprocess argument (see worker.py). Local disk yields the stored
        path itself with no copy; S3 downloads to an isolated temporary
        file and always removes it on the way out, success or failure, so
        a Railway container's small disk cannot fill up."""

    @abstractmethod
    def open_stream(self, key: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        """Yield `key`'s bytes from `start` to `end` INCLUSIVE (HTTP Range
        semantics, RFC 7233 -- not Python slice semantics), or to the end
        of the object when `end` is None. Backs ranged evidence serving
        (video seeking) without loading a whole video into memory."""


class LocalDiskStorage(Storage):
    """Private local volume. Keys are relative paths, e.g.
    'assessments/{id}/{task_code}/{evidence_id}.mp4'."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        root = self.root.resolve()
        if root not in path.parents and path != root:
            raise ValueError(f"key escapes storage root: {key}")
        return path

    def write(self, key: str, data: bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    def write_once(self, key: str, data: bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".report-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            # A same-filesystem hard link is atomic and never replaces a key.
            os.link(temporary, path)
        finally:
            os.unlink(temporary)
        return hashlib.sha256(data).hexdigest()

    def append(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as f:
            f.write(data)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def size(self, key: str) -> int:
        path = self._path(key)
        return path.stat().st_size if path.exists() else 0

    def sha256(self, key: str) -> str:
        h = hashlib.sha256()
        with self._path(key).open("rb") as f:
            for chunk in iter(lambda: f.read(_READ_CHUNK), b""):
                h.update(chunk)
        return h.hexdigest()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def path_for(self, key: str) -> Path:
        """Real filesystem path for this key -- only meaningful for a local
        disk backend (a future S3/MinIO Storage wouldn't have one). Used
        where something genuinely needs a path: serving via Starlette's
        FileResponse (Range-request support, see routers/evidence.py) and
        invoking ffmpeg as a subprocess (see worker.py)."""
        return self._path(key)

    def probe(self) -> bool:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe = self.root / ".health_probe"
            probe.write_text("ok")
            probe.unlink()
            return True
        except OSError:
            return False

    @contextmanager
    def local_path(self, key: str) -> Iterator[Path]:
        """Already a real file -- yield it directly. No copy, and
        deliberately no deletion: this IS the stored evidence."""
        yield self._path(key)

    def open_stream(self, key: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        path = self._path(key)
        remaining = (end - start + 1) if end is not None else None
        with path.open("rb") as f:
            f.seek(start)
            while remaining is None or remaining > 0:
                want = _READ_CHUNK if remaining is None else min(_READ_CHUNK, remaining)
                data = f.read(want)
                if not data:
                    return
                if remaining is not None:
                    remaining -= len(data)
                yield data



# S3 multipart's hard floor: every part except the last must be >= 5 MiB.
# PARAKH streams 1 MiB chunks (UPLOAD_CHUNK_MAX_BYTES caps them at 2 MiB),
# so a part-per-chunk multipart upload would be rejected outright at
# completion -- which is exactly why chunks are staged as discrete objects
# first and coalesced into >= 5 MiB parts only at finalize() time.
_MIN_PART_BYTES = 5 * 1024 * 1024
_STAGING_SUFFIX = ".staging/"


class S3Storage(Storage):
    """S3-compatible private evidence storage (Neon Object Storage, MinIO,
    or any S3 API), for a hosted deployment where the API and the worker
    are separate containers on ephemeral disks and therefore cannot share
    the LocalDiskStorage volume that infra/docker-compose.yml gives them.

    The one genuinely hard problem here is append(). S3 objects are
    immutable: there is no append, and re-uploading the whole growing
    object once per 1 MiB chunk would make a 120 MB video cost ~7 GB of
    transfer (O(n^2)) -- unusable on a free tier. S3's native answer,
    multipart upload, does not fit either: it requires every part except
    the last to be at least 5 MiB, and PARAKH's chunks are 1-2 MiB.

    So each chunk is instead PUT as its own small, immediately durable
    staging object under "{key}.staging/{seq:08d}". That gives exactly the
    properties the resumable protocol needs:

      * durable per chunk -- an API restart mid-upload loses nothing, and
        the client resumes from the session's next_chunk_index as always;
      * bounded memory -- only the one chunk is ever held;
      * no O(n^2) rewrite -- each byte is uploaded once here;
      * ordered -- zero-padded sequence numbers sort lexicographically in
        the same order they sort numerically, so a plain list_objects_v2
        returns the chunks in upload order.

    finalize() then coalesces the staging objects into the single object at
    `key` via one multipart upload, buffering them into >= 5 MiB parts, and
    deletes the staging objects. That is one extra read+write of the
    object's bytes, once, at completion -- not per chunk.

    Chunk-index validation, replay idempotency and out-of-order rejection
    are NOT re-implemented here: routers/uploads.py already enforces them
    against the upload session row under a row lock, and that remains the
    single source of truth for both backends.
    """

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        region: str = "auto",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ):
        # Imported lazily and NOT at module scope on purpose: the default
        # local backend, the offline/LAN deployment and the existing test
        # suite must all keep working without boto3 installed at all.
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                signature_version="s3v4",
                # Neon Object Storage supports PATH-style addressing only
                # (https://neon.com/docs/storage/s3-compatibility). boto3
                # would otherwise default to virtual-hosted style for a
                # custom endpoint and send every request to
                # "{bucket}.{endpoint}", which does not resolve. MinIO and
                # real AWS S3 both accept path style too, so this is safe
                # across backends rather than Neon-specific.
                s3={"addressing_style": "path"},
                retries={"max_attempts": 5, "mode": "standard"},
            ),
        )

    # --- internals -------------------------------------------------------

    def _staging_prefix(self, key: str) -> str:
        return f"{key}{_STAGING_SUFFIX}"

    def _staged(self, key: str) -> list[dict]:
        """Every staging object for `key`, in upload order. Paginated: a
        120 MB upload in 1 MiB chunks is 120 objects, under the 1000-key
        default page, but never rely on that."""
        prefix = self._staging_prefix(key)
        out: list[dict] = []
        token: str | None = None
        while True:
            kwargs = {"Bucket": self.bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            page = self._client.list_objects_v2(**kwargs)
            out.extend(page.get("Contents", []))
            if not page.get("IsTruncated"):
                break
            token = page.get("NextContinuationToken")
        out.sort(key=lambda o: o["Key"])
        return out

    def _head(self, key: str) -> dict | None:
        from botocore.exceptions import ClientError
        try:
            return self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise

    def _delete_keys(self, keys: list[str]) -> None:
        for i in range(0, len(keys), 1000):
            self._client.delete_objects(
                Bucket=self.bucket,
                Delete={"Objects": [{"Key": k} for k in keys[i : i + 1000]], "Quiet": True},
            )

    def _iter_object(self, key: str, range_header: str | None = None) -> Iterator[bytes]:
        kwargs = {"Bucket": self.bucket, "Key": key}
        if range_header:
            kwargs["Range"] = range_header
        body = self._client.get_object(**kwargs)["Body"]
        try:
            while True:
                data = body.read(_READ_CHUNK)
                if not data:
                    return
                yield data
        finally:
            body.close()

    def _iter_assembled(self, key: str) -> Iterator[bytes]:
        """`key`'s bytes whether or not it has been finalized yet -- the
        finalized object if it exists, otherwise its staging objects in
        order. Lets size()/sha256()/read() work mid-upload exactly as they
        do on local disk, which routers/uploads.py relies on."""
        if self._head(key) is not None:
            yield from self._iter_object(key)
            return
        for obj in self._staged(key):
            yield from self._iter_object(obj["Key"])

    # --- Storage ---------------------------------------------------------

    def write(self, key: str, data: bytes) -> str:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return hashlib.sha256(data).hexdigest()

    def write_once(self, key: str, data: bytes) -> str:
        # Fail closed on providers without conditional PUT support. Never fall
        # back to an overwriting PUT for a signed artifact.
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data,
                                ContentType="application/pdf", IfNoneMatch="*")
        return hashlib.sha256(data).hexdigest()

    def append(self, key: str, data: bytes) -> None:
        seq = len(self._staged(key))
        self._client.put_object(
            Bucket=self.bucket, Key=f"{self._staging_prefix(key)}{seq:08d}", Body=data
        )

    def read(self, key: str) -> bytes:
        return b"".join(self._iter_assembled(key))

    def size(self, key: str) -> int:
        head = self._head(key)
        if head is not None:
            return head["ContentLength"]
        return sum(o["Size"] for o in self._staged(key))

    def sha256(self, key: str) -> str:
        h = hashlib.sha256()
        for block in self._iter_assembled(key):
            h.update(block)
        return h.hexdigest()

    def exists(self, key: str) -> bool:
        return self._head(key) is not None or bool(self._staged(key))

    def delete(self, key: str) -> None:
        """Removes the finalized object AND any staging objects -- so the
        defensive pre-upload cleanup in routers/uploads.py cannot leave a
        previous attempt's chunks to be silently prepended onto this
        session's bytes, and an expired/abandoned session leaves no
        orphaned objects behind."""
        keys = [o["Key"] for o in self._staged(key)]
        if self._head(key) is not None:
            keys.append(key)
        if keys:
            self._delete_keys(keys)

    def probe(self) -> bool:
        """A real write+delete round-trip, not just head_bucket: readable-
        but-not-writable credentials are a configuration mistake /health
        must surface before a worker tries to store a thumbnail."""
        try:
            key = ".health_probe"
            self._client.put_object(Bucket=self.bucket, Key=key, Body=b"ok")
            self._client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def finalize(self, key: str, content_type: str | None = None) -> None:
        if self._head(key) is not None:
            # Already assembled -- a replayed complete(). Just make sure no
            # staging objects survive to be charged for or re-read.
            staged = [o["Key"] for o in self._staged(key)]
            if staged:
                self._delete_keys(staged)
            return

        staged = self._staged(key)
        extra = {"ContentType": content_type} if content_type else {}

        if not staged:
            self._client.put_object(Bucket=self.bucket, Key=key, Body=b"", **extra)
            return

        if len(staged) == 1:
            # Single-chunk upload (every photo, most manifests): a server-
            # side copy beats a multipart upload and never touches 5 MiB.
            # MetadataDirective=REPLACE is required: a plain copy_object
            # silently keeps the SOURCE object's metadata, so the declared
            # MIME would be lost and every photo would finalize as
            # binary/octet-stream.
            self._client.copy_object(
                Bucket=self.bucket,
                Key=key,
                CopySource={"Bucket": self.bucket, "Key": staged[0]["Key"]},
                MetadataDirective="REPLACE" if content_type else "COPY",
                **extra,
            )
            self._delete_keys([staged[0]["Key"]])
            return

        upload_id = self._client.create_multipart_upload(
            Bucket=self.bucket, Key=key, **extra
        )["UploadId"]
        try:
            parts: list[dict] = []
            buf = bytearray()

            def flush() -> None:
                nonlocal buf
                result = self._client.upload_part(
                    Bucket=self.bucket, Key=key, UploadId=upload_id,
                    PartNumber=len(parts) + 1, Body=bytes(buf),
                )
                parts.append({"PartNumber": len(parts) + 1, "ETag": result["ETag"]})
                buf = bytearray()

            for obj in staged:
                for block in self._iter_object(obj["Key"]):
                    buf.extend(block)
                    # Coalesce into >= 5 MiB parts. Peak memory is one part
                    # plus one read block, not the whole object.
                    if len(buf) >= _MIN_PART_BYTES:
                        flush()
            if buf:
                flush()  # trailing part -- the only one allowed under 5 MiB

            self._client.complete_multipart_upload(
                Bucket=self.bucket, Key=key, UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
        except Exception:
            # Never leave a half-finished multipart upload accruing
            # storage: abort it, keep the staging objects so the client can
            # still retry complete(), and re-raise.
            self._client.abort_multipart_upload(
                Bucket=self.bucket, Key=key, UploadId=upload_id
            )
            raise

        self._delete_keys([o["Key"] for o in staged])

    @contextmanager
    def local_path(self, key: str) -> Iterator[Path]:
        fd, tmp = tempfile.mkstemp(prefix="parakh-evidence-")
        try:
            with os.fdopen(fd, "wb") as f:
                for block in self._iter_assembled(key):
                    f.write(block)
            yield Path(tmp)
        finally:
            # Always, including on ffmpeg failure -- Railway's container
            # disk is small and this runs once per evidence item.
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass

    def open_stream(self, key: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        if self._head(key) is None:
            # Not yet finalized: fall back to walking the staging objects
            # and slicing locally. Only reachable for an in-progress
            # upload, never for served evidence.
            pos = 0
            want_end = end
            for block in self._iter_assembled(key):
                block_end = pos + len(block) - 1
                if block_end >= start and (want_end is None or pos <= want_end):
                    lo = max(0, start - pos)
                    hi = len(block) if want_end is None else min(len(block), want_end - pos + 1)
                    if hi > lo:
                        yield block[lo:hi]
                pos = block_end + 1
                if want_end is not None and pos > want_end:
                    return
            return
        header = f"bytes={start}-" if end is None else f"bytes={start}-{end}"
        yield from self._iter_object(key, range_header=header)


def get_storage() -> Storage:
    """The one place a backend is chosen. STORAGE_BACKEND defaults to
    "local", so Docker Compose, the offline/LAN deployment and every
    existing test keep the exact LocalDiskStorage behaviour they had, with
    no cloud credential required anywhere."""
    from .config import settings  # local import: keeps this module importable without config

    if settings.storage_backend == "s3":
        return S3Storage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
        )
    return LocalDiskStorage(settings.evidence_dir)


_EXTENSION_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}


def extension_for_mime(mime: str) -> str:
    return _EXTENSION_BY_MIME.get(mime, ".bin")


def upload_key_for(assessment_id: int, task_code: str, session_id: int) -> str:
    """In-progress (and, once completed, final) storage key for a resumable
    upload session. Server-generated -- never a client-supplied filename."""
    return f"assessments/{assessment_id}/{task_code}/uploads/{session_id}.part"


def manifest_upload_key_for(assessment_id: int, session_id: int) -> str:
    """Storage key for a P6 manifest-target upload session (not task-scoped
    -- see UploadSession.target in models.py)."""
    return f"assessments/{assessment_id}/sync/manifest/{session_id}.part"
