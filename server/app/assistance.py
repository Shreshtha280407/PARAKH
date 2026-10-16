"""Versioned signed ON_DEVICE assistance. Advisory data never feeds scoring.

The JSON schema is exported to contracts/flags.schema.json from these strict
models. Structural validation plus evidence binding runs only after signature
verification. No server inference or unsigned ingestion path exists.
"""
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Status = Literal["NOT_RUN", "QUEUED", "RUNNING", "COMPLETED", "PARTIAL", "FAILED", "UNAVAILABLE"]
ResultStatus = Literal["COMPLETED", "PARTIAL", "FAILED", "UNAVAILABLE"]
FlagType = Literal["DARK", "OVEREXPOSED", "BLURRY", "CAMERA_MOTION", "HANDS_NOT_DETECTED"]
Error = Literal["CANCELLED", "INTERRUPTED", "MEDIA_UNAVAILABLE", "INPUT_CHANGED", "ANALYSIS_FAILED", "MODEL_UNAVAILABLE", "INCOMPLETE_COVERAGE", "PAYLOAD_LIMIT"]
Identifier = Annotated[str, Field(min_length=1, max_length=64)]
Version = Annotated[str, Field(min_length=1, max_length=80)]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Time = Annotated[int, Field(strict=True, ge=0, le=1_200_000)]
Ratio = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Metric = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class AssistanceFlag(StrictModel):
    type: FlagType
    startMs: Time = 0
    endMs: Time | None = None
    severity: Literal["review"] = "review"
    observed: Metric | None = None
    threshold: Metric | None = None

    @model_validator(mode="after")
    def ordered(self):
        if self.endMs is not None and self.endMs <= self.startMs:
            raise ValueError("interval must have positive length")
        return self


class AssistanceProvenance(StrictModel):
    moduleVersion: Version
    profileVersion: Version
    profileSha256: Hash
    modelSha256: Hash | None = None
    sampleIntervalMs: Literal[1000] = 1000

    @field_validator("sampleIntervalMs", mode="before")
    @classmethod
    def integer_interval(cls, value):
        if type(value) is not int:
            raise ValueError("sample interval must be an integer")
        return value


class AssistanceCoverage(StrictModel):
    requestedSamples: Annotated[int, Field(strict=True, ge=0, le=2400)]
    analysedSamples: Annotated[int, Field(strict=True, ge=0, le=2400)]
    coveredDurationMs: Time
    motionRequestedPairs: Annotated[int, Field(strict=True, ge=0, le=1200)] = 0
    motionAnalysedPairs: Annotated[int, Field(strict=True, ge=0, le=1200)] = 0

    @model_validator(mode="after")
    def counts(self):
        if self.analysedSamples > self.requestedSamples or self.motionAnalysedPairs > self.motionRequestedPairs:
            raise ValueError("analysed count exceeds requested count")
        return self


class AssistanceAnalysis(StrictModel):
    status: ResultStatus
    provenance: AssistanceProvenance | None
    coverage: AssistanceCoverage
    reviewRecommended: bool | None = None
    visibleRatio: Ratio | None = None
    visibleRatioGapFilled: Ratio | None = None

    @model_validator(mode="after")
    def result(self):
        if self.status in ("COMPLETED", "PARTIAL"):
            if self.provenance is None or self.coverage.analysedSamples == 0:
                raise ValueError("usable analysis requires provenance and observations")
        elif any(v is not None for v in (self.reviewRecommended, self.visibleRatio, self.visibleRatioGapFilled)) or self.coverage.analysedSamples:
            raise ValueError("failed/unavailable analysis cannot claim observations")
        return self


class AssistanceSnapshot(StrictModel):
    contractVersion: Literal[1] = 1
    source: Literal["ON_DEVICE"] = "ON_DEVICE"
    assessmentId: Identifier
    taskId: Literal["T1", "T2", "T3", "T4", "T5"]
    evidenceId: Identifier
    revisionId: Identifier
    revisionNumber: Annotated[int, Field(strict=True, ge=1)]
    mediaSha256: Hash
    durationMs: Annotated[int, Field(strict=True, ge=1, le=9_007_199_254_740_991)] | None = None
    status: Status
    quality: AssistanceAnalysis | None = None
    hands: AssistanceAnalysis | None = None
    flags: Annotated[list[AssistanceFlag], Field(max_length=256)] = []
    completedAtMillis: Annotated[int, Field(strict=True, ge=0, le=9_007_199_254_740_991)] | None = None
    errorCategory: Error | None = None
    intervalsTruncated: bool = False

    @field_validator("contractVersion", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("contract version must be an integer")
        return value

    @model_validator(mode="after")
    def semantics(self):
        if len({f.model_dump_json() for f in self.flags}) != len(self.flags):
            raise ValueError("duplicate flags")
        for flag in self.flags:
            if self.durationMs is None:
                if flag.startMs != 0 or flag.endMs is not None or flag.type in ("HANDS_NOT_DETECTED", "CAMERA_MOTION"):
                    raise ValueError("photo flags have no temporal interval")
            elif flag.endMs is None or flag.startMs >= self.durationMs or flag.endMs > self.durationMs:
                raise ValueError("flag outside signed evidence duration")
            analysis = self.hands if flag.type == "HANDS_NOT_DETECTED" else self.quality
            if analysis is None or analysis.status not in ("COMPLETED", "PARTIAL"):
                raise ValueError("flag requires usable source analysis")
        for component in (self.quality, self.hands):
            if component and component.coverage.coveredDurationMs > (self.durationMs or 0):
                raise ValueError("coverage exceeds evidence duration")
        if self.durationMs is None and self.hands is not None:
            raise ValueError("production hands analysis is video only")
        if self.hands and self.hands.status in ("COMPLETED", "PARTIAL") and not self.hands.provenance.modelSha256:
            raise ValueError("hands analysis requires model hash")
        if self.quality and (self.quality.visibleRatio is not None or self.quality.visibleRatioGapFilled is not None or self.quality.provenance and self.quality.provenance.modelSha256):
            raise ValueError("quality analysis cannot claim hand observations")
        if self.hands and self.hands.reviewRecommended is not None:
            raise ValueError("hands detection is not a quality verdict")
        if self.status in ("NOT_RUN", "QUEUED", "RUNNING") and (self.quality or self.hands or self.flags or self.completedAtMillis is not None):
            raise ValueError("pending state cannot contain results")
        if self.status == "COMPLETED" and (not self.quality or self.quality.status != "COMPLETED" or self.durationMs is not None and (not self.hands or self.hands.status != "COMPLETED")):
            raise ValueError("completed snapshot requires completed components")
        if self.status in ("COMPLETED", "PARTIAL") and self.completedAtMillis is None:
            raise ValueError("usable snapshot requires completion time")
        usable = any(c and c.status in ("COMPLETED", "PARTIAL") for c in (self.quality, self.hands))
        if self.status == "PARTIAL" and not usable:
            raise ValueError("partial snapshot requires usable observations")
        if self.status in ("FAILED", "UNAVAILABLE") and (usable or self.flags):
            raise ValueError("failed/unavailable snapshot cannot claim observations")
        if self.intervalsTruncated and (self.status != "PARTIAL" or self.errorCategory != "PAYLOAD_LIMIT"):
            raise ValueError("truncated intervals require explicit partial/payload-limit state")
        return self


def validate_snapshot(raw: dict, *, assessment_id: str, revision_id: str, item: dict) -> dict:
    if len(json.dumps(raw, allow_nan=False, separators=(",", ":")).encode()) > 65536:
        raise ValueError("assistance exceeds 65536-byte ceiling")
    value = AssistanceSnapshot.model_validate(raw)
    if (value.assessmentId, value.taskId, value.evidenceId, value.mediaSha256) != (
        assessment_id, item["taskId"], item["evidenceId"], item["sha256"],
    ):
        raise ValueError("assistance evidence binding mismatch")
    if item.get("processing") != "INHERITED" and value.revisionId != revision_id:
        raise ValueError("assistance revision binding mismatch")
    if value.durationMs != item.get("durationMillis") or (item["kind"].lower() == "video") != (value.durationMs is not None):
        raise ValueError("assistance media kind/duration mismatch")
    return value.model_dump()
