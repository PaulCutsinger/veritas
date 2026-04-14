"""
tests/test_entropy.py
----------------------
Tests for the render entropy calculation in pipeline.py.
Uses PIL to generate synthetic images — no Isaac Sim required.
"""

from __future__ import annotations

from pathlib import Path

from veritas.core.pipeline import _image_entropy


def _write_solid_black(path: Path) -> None:
    from PIL import Image

    img = Image.new("RGB", (256, 256), color=(0, 0, 0))
    img.save(str(path))


def _write_solid_colour(path: Path, colour: tuple) -> None:
    from PIL import Image

    img = Image.new("RGB", (256, 256), color=colour)
    img.save(str(path))


def _write_random_noise(path: Path) -> None:
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(42)
    arr = rng.integers(0, 256, (256, 256, 3), dtype=np.uint8)
    Image.fromarray(arr).save(str(path))


def _write_gradient(path: Path) -> None:
    import numpy as np
    from PIL import Image

    arr = np.tile(np.arange(256, dtype=np.uint8), (256, 1))
    Image.fromarray(arr).save(str(path))


class TestImageEntropy:
    def test_black_frame_entropy_near_zero(self, tmp_path):
        p = tmp_path / "black.png"
        _write_solid_black(p)
        e = _image_entropy(str(p))
        assert e < 0.01, f"Black frame entropy should be ~0, got {e}"

    def test_solid_colour_entropy_near_zero(self, tmp_path):
        p = tmp_path / "solid.png"
        _write_solid_colour(p, (128, 64, 200))
        e = _image_entropy(str(p))
        assert e < 0.01, f"Solid colour entropy should be ~0, got {e}"

    def test_random_noise_entropy_high(self, tmp_path):
        p = tmp_path / "noise.png"
        _write_random_noise(p)
        e = _image_entropy(str(p))
        assert e > 5.0, f"Random noise entropy should be high, got {e}"

    def test_gradient_entropy_intermediate(self, tmp_path):
        p = tmp_path / "gradient.png"
        _write_gradient(p)
        e = _image_entropy(str(p))
        # Gradient has all 256 values equally → entropy = log2(256) = 8
        assert e > 4.0, f"Gradient entropy should be intermediate/high, got {e}"

    def test_entropy_range(self, tmp_path):
        p = tmp_path / "noise.png"
        _write_random_noise(p)
        e = _image_entropy(str(p))
        assert 0.0 <= e <= 8.0

    def test_missing_file_returns_zero(self):
        e = _image_entropy("/nonexistent/image.png")
        assert e == 0.0

    def test_pipeline_threshold_black_frame(self, tmp_path):
        """Pipeline must FAIL a real black frame image."""
        import time

        from veritas.core.models import RenderResult, UsdAuditResult, Verdict
        from veritas.core.pipeline import VeritasPipeline
        from veritas.interface.renderer import Renderer
        from veritas.interface.usd_auditor import UsdAuditor

        black_img = tmp_path / "black.png"
        _write_solid_black(black_img)

        class _FakeAuditor(UsdAuditor):
            def audit(self, s):
                return UsdAuditResult(stage_path=s, prim_count=0, prims=[], schema_violations=[])

        class _FakeRenderer(Renderer):
            def render(self, stage_path, output_path):
                from shutil import copy

                copy(str(black_img), output_path)
                size = black_img.stat().st_size
                # Compute real entropy — pipeline does this separately, but we set it honestly
                entropy = _image_entropy(str(black_img))
                return RenderResult(
                    image_path=output_path,
                    file_size_bytes=size,
                    timestamp=time.time(),
                    entropy=entropy,
                    valid=True,
                )

        pipeline = VeritasPipeline(
            auditor=_FakeAuditor(),
            renderer=_FakeRenderer(),
            output_dir=str(tmp_path / "out"),
        )
        report = pipeline.run("/fake/factory.usd")
        # Black PNG is very small (< 10 KB) OR entropy = 0 — either triggers FAIL
        assert report.verdict == Verdict.FAIL
