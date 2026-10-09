import datetime

from pydantic import BaseModel, ConfigDict


class HealthOut(BaseModel):
    status: str
    database: str


class AssessmentCreate(BaseModel):
    worker_id: int
    pack_id: int


class AssessmentTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    task_code: str
    budget_bytes: int
    bytes_used: int
    status: str


class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    worker_id: int
    pack_id: int
    status: str
    total_bytes_used: int
    created_at: datetime.datetime
    tasks: list[AssessmentTaskOut]


class EvidenceItemCreate(BaseModel):
    task_code: str
    kind: str  # photo | video
    mime: str
    declared_size_bytes: int


class EvidenceItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    mime: str
    declared_size_bytes: int
    created_at: datetime.datetime


class UploadSessionCreate(BaseModel):
    assessment_id: int
    task_code: str
    claimed_size_bytes: int


class UploadSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    assessment_task_id: int
    claimed_size_bytes: int
    status: str
    opened_at: datetime.datetime
    task_bytes_remaining: int
    total_bytes_remaining: int


class QueueItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    worker_id: int
    worker_name: str
    pack_code: str
    status: str
    created_at: datetime.datetime
