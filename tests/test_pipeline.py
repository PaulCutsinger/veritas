"""
tests/test_pipeline.py
-----------------------
Tests for VeritasPipeline using mock auditor and renderer.
No Isaac Sim, Anthropic API, or real USD files required.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from veritas.core.models import (
    PrimInfo,
    RenderResult,
    UsdAuditResult,
    Verdict,
    VisionResult,
    SegmentResult,
)
from veritas.core.pipeline import VeritasPipeline
from veritas.interface.renderer import Renderer
from veritas.interface.usd_auditor import UsdAuditor
from veritas.interface.vision_backend import VisionBackend
from veritas.interface.segmentor import Segmentor


# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------

class _MockAuditor(UsdAuditor):
    def __init__(self, violations: list[str] | None = None):
        self._violations = violations or []

    def audit(self, stage_path: str) -> UsdAuditResult:
        prims = [
            PrimInfo(path="/World", type="Xform"),
            PrimInfo(path="/World/Robot", type="Xform"),
        ]
        return UsdAuditResult(
            stage_path=stage_path,
            prim_count=len(prims),
            prims=prims,
            schema_violations=self._violations,
        )


class _MockRenderer(Renderer):
    def __init__(self, file_size: int = 200_000, entropy: float = 4.0, valid: bool = True):
        self._file_size = file_size
        self._entropy = entropy
        self._valid = valid

    def render(self, stage_path: str, output_path: str) -> RenderResult:
        # Write a dummy file so downstream code (if any) can stat it
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"\x89PNG" + b"\xff" * self._file_size)
        return RenderResult(
            image_path=output_path,
            file_size_bytes=self._file_size,
            timestamp=time.time(),
            entropy=self._entropy,
            valid=self._valid,
        )


class _MockVision(VisionBackend):
    def describe(self, image_path: str, context: str = "") -> VisionResult:
        return VisionResult(
            description="A factory floor with a FANUC robot arm.",
            entities=["robot_arm", "floor"],
        )


class _MockSegmentor(Segmentor):
    def segment(self, image_path: str, labels: list[str] | None = None) -> SegmentResult:
        return SegmentResult(
            image_path=image_path,
            masks=[{"bbox": [0, 0, 100, 100], "score": 0.9}],
            labels=["robot_arm"],
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestVeritasPipelinePass:
    def test_pass_with_valid_render(self, tmp_path):
        pipeline = VeritasPipeline(
            auditor=_MockAuditor(),
            renderer=_MockRenderer(),
            output_dir=str(tmp_path / "out"),
        )
        report = pipeline.run("/fake/factory.usd")

        assert report.verdict == Verdict.PASS
        assert report.usd_audit.prim_count == 2
        assert report.render.valid is True
        assert report.vision is None
        assert report.segmentation is None

    def test_pass_with_vision_and_segmentation(self, tmp_path):
        pipeline = VeritasPipeline(
            auditor=_MockAuditor(),
            renderer=_MockRenderer(),
            vision=_MockVision(),
            segmentor=_MockSegmentor(),
            output_dir=str(tmp_path / "out"),
        )
        report = pipeline.run("/fake/factory.usd")

        assert report.verdict == Verdict.PASS
        assert report.vision is not None
        assert "robot_arm" in report.vision.entities
        assert report.segmentation is not None
        assert report.segmentation.labels == ["robot_arm"]


class TestVeritasPipelineFail:
    def test_fail_on_small_render(self, tmp_path):
        """Render file smaller than 10 KB threshold should produce FAIL."""
        pipeline = VeritasPipeline(
            auditor=_MockAuditor(),
            renderer=_MockRenderer(file_size=512),  # 512 bytes < 10 KB
            output_dir=str(tmp_path / "out"),
        )
        report = pipeline.run("/fake/factory.usd")

        assert report.verdict == Verdict.FAIL
        assert "too small" in report.reason.lower()

    def test_fail_on_low_entropy(self, tmp_path):
        """Render with entropy <= 0.5 (solid colour/black frame) should FAIL."""
        pipeline = VeritasPipeline(
            auditor=_MockAuditor(),
            renderer=_MockRenderer(file_size=200_000, entropy=0.1),
            output_dir=str(tmp_path / "out"),
        )
        report = pipeline.run("/fake/factory.usd")

        assert report.verdict == Verdict.FAIL
        assert "entropy" in report.reason.lower()


class TestVeritasPipelineWarn:
    def test_warn_on_schema_violations(self, tmp_path):
        """USD audit violations with a valid render should produce WARN."""
        pipeline = VeritasPipeline(
            auditor=_MockAuditor(violations=["missing UsdPhysics on /World/Robot"]),
            renderer=_MockRenderer(),
            output_dir=str(tmp_path / "out"),
        )
        report = pipeline.run("/fake/factory.usd")

        assert report.verdict == Verdict.WARN
        assert "violation" in report.reason.lower()


class TestVeritasPipelineOutputDir:
    def test_output_dir_created(self, tmp_path):
        out_dir = tmp_path / "nested" / "veritas_out"
        pipeline = VeritasPipeline(
            auditor=_MockAuditor(),
            renderer=_MockRenderer(),
            output_dir=str(out_dir),
        )
        pipeline.run("/fake/factory.usd")
        assert out_dir.exists()

    def test_render_image_written(self, tmp_path):
        out_dir = tmp_path / "out"
        pipeline = VeritasPipeline(
            auditor=_MockAuditor(),
            renderer=_MockRenderer(),
            output_dir=str(out_dir),
        )
        report = pipeline.run("/fake/factory.usd")
        assert Path(report.render.image_path).exists()
