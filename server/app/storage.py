"""Private evidence storage interface (master plan p.7: "Private Docker
volume behind a Storage interface ... swap to S3/MinIO later without code
changes elsewhere"). Only the interface + a local-disk implementation exist
in P2 -- no caller writes real evidence bytes through it yet (that's the
upload-bytes path, explicitly out of P2 scope).
"""
import hashlib
from abc import ABC, abstractmethod
from pathlib import Path


class Storage(ABC):
    @abstractmethod
    def write(self, key: str, data: bytes) -> str:
        """Write data under key, return its sha256 hex digest."""

    @abstractmethod
    def read(self, key: str) -> bytes: ...

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
        if self.root.resolve() not in path.parents and path != self.root.resolve():
            raise ValueError(f"key escapes storage root: {key}")
        return path

    def write(self, key: str, data: bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()


def key_for(assessment_id: int, task_code: str, evidence_id: int, extension: str) -> str:
    return f"assessments/{assessment_id}/{task_code}/{evidence_id}{extension}"
