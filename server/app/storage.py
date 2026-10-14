"""Private evidence storage interface (master plan p.7: "Private Docker
volume behind a Storage interface ... swap to S3/MinIO later without code
changes elsewhere"). Mounted as a private volume in Docker (infra/docker-
compose.yml) -- never exposed via a public/writable static file route.

Keys are server-generated (see upload_key_for / evidence_key_for); client
filenames are never used as paths, to rule out path traversal and
collisions.
"""
import hashlib
from abc import ABC, abstractmethod
from pathlib import Path

_READ_CHUNK = 1024 * 1024


class Storage(ABC):
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
