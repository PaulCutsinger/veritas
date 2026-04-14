"""
veritas.core.models
-------------------
Shared data models for the Veritas USD validation pipeline.
"""
from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, Field


class PrimInfo(BaseModel):
    path: str
    type: str
    transform: list[float] = Field(default_factory=list)


class UsdAuditResult(BaseModel):
    stage_path: str
    prim_count: int
    prims: list[PrimInfo] = Field(default_factory=list)
    schema_violations: list[str] = Field(default_factory=list)


class RenderResult(BaseModel):
    image_path: str
    file_size_bytes: int
    timestamp: float
    entropy: float
    valid: bool


class SegmentResult(BaseModel):
    image_path: str
    masks: list[dict[str, Any]] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)


class VisionResult(BaseModel):
    description: str
    entities: list[str] = Field(default_factory=list)


class Verdict(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"


class VeritasReport(BaseModel):
    usd_audit: UsdAuditResult
    render: RenderResult
    vision: VisionResult | None = None
    segmentation: SegmentResult | None = None
    verdict: Verdict
    reason: str
