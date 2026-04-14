"""
tests/test_models.py
---------------------
Unit tests that verify Pydantic models instantiate correctly.
No Isaac Sim, Anthropic API, or filesystem access required.
"""
import time

import pytest

from veritas.core.models import (
    PrimInfo,
    RenderResult,
    SegmentResult,
    UsdAuditResult,
    VeritasReport,
    Verdict,
    VisionResult,
)


class TestPrimInfo:
    def test_minimal(self):
        p = PrimInfo(path="/World/Robot", type="Xform")
        assert p.path == "/World/Robot"
        assert p.type == "Xform"
        assert p.transform == []

    def test_with_transform(self):
        xform = [1.0] * 16
        p = PrimInfo(path="/World/Box", type="Cube", transform=xform)
        assert len(p.transform) == 16


class TestUsdAuditResult:
    def test_minimal(self):
        r = UsdAuditResult(stage_path="/tmp/test.usd", prim_count=0)
        assert r.prim_count == 0
        assert r.prims == []
        assert r.schema_violations == []

    def test_with_prims(self):
        p = PrimInfo(path="/World", type="Xform")
        r = UsdAuditResult(
            stage_path="/tmp/test.usd",
            prim_count=1,
            prims=[p],
            schema_violations=["missing physics"],
        )
        assert r.prim_count == 1
        assert len(r.prims) == 1
        assert r.schema_violations == ["missing physics"]


class TestRenderResult:
    def test_valid_render(self):
        r = RenderResult(
            image_path="/tmp/render.png",
            file_size_bytes=512000,
            timestamp=time.time(),
            entropy=3.5,
            valid=True,
        )
        assert r.valid is True

    def test_invalid_render(self):
        r = RenderResult(
            image_path="/tmp/black.png",
            file_size_bytes=512,
            timestamp=time.time(),
            entropy=0.0,
            valid=False,
        )
        assert r.valid is False
        assert r.entropy == 0.0


class TestSegmentResult:
    def test_minimal(self):
        s = SegmentResult(image_path="/tmp/render.png")
        assert s.masks == []
        assert s.labels == []

    def test_with_masks(self):
        mask = {"bbox": [10, 20, 100, 200], "score": 0.95}
        s = SegmentResult(image_path="/tmp/render.png", masks=[mask], labels=["robot_arm"])
        assert len(s.masks) == 1
        assert s.labels == ["robot_arm"]


class TestVisionResult:
    def test_minimal(self):
        v = VisionResult(description="A factory floor with a robot arm.")
        assert v.entities == []

    def test_with_entities(self):
        v = VisionResult(
            description="Robot arm on conveyor.",
            entities=["robot_arm", "conveyor"],
        )
        assert "robot_arm" in v.entities


class TestVerdict:
    def test_values(self):
        assert Verdict.PASS == "PASS"
        assert Verdict.FAIL == "FAIL"
        assert Verdict.WARN == "WARN"

    def test_enum_membership(self):
        assert Verdict("PASS") is Verdict.PASS


class TestVeritasReport:
    def _audit(self):
        return UsdAuditResult(stage_path="/tmp/test.usd", prim_count=5)

    def _render(self):
        return RenderResult(
            image_path="/tmp/render.png",
            file_size_bytes=200000,
            timestamp=time.time(),
            entropy=4.0,
            valid=True,
        )

    def test_minimal_pass(self):
        report = VeritasReport(
            usd_audit=self._audit(),
            render=self._render(),
            verdict=Verdict.PASS,
            reason="All checks passed.",
        )
        assert report.verdict == Verdict.PASS
        assert report.vision is None
        assert report.segmentation is None

    def test_with_optional_fields(self):
        vision = VisionResult(description="Looks good.", entities=["shelf"])
        seg = SegmentResult(image_path="/tmp/render.png", labels=["shelf"])
        report = VeritasReport(
            usd_audit=self._audit(),
            render=self._render(),
            vision=vision,
            segmentation=seg,
            verdict=Verdict.WARN,
            reason="Schema violations found.",
        )
        assert report.vision is not None
        assert report.segmentation is not None
        assert report.verdict == Verdict.WARN

    def test_serialise_json(self):
        report = VeritasReport(
            usd_audit=self._audit(),
            render=self._render(),
            verdict=Verdict.FAIL,
            reason="Render too small.",
        )
        data = report.model_dump_json()
        assert "FAIL" in data
        assert "Render too small" in data
