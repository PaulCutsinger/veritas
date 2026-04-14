"""
veritas.core.pipeline
----------------------
The VeritasPipeline orchestrates the 6-step validation loop:

  USD audit → render → render-validate → segment → vision → verdict
"""
from __future__ import annotations

import math
import os
import time
from pathlib import Path

from .models import RenderResult, Verdict, VeritasReport
from ..interface.renderer import Renderer
from ..interface.segmentor import Segmentor
from ..interface.sim_validator import SimValidator
from ..interface.usd_auditor import UsdAuditor
from ..interface.vision_backend import VisionBackend

# Thresholds for render validity checks
_MIN_FILE_SIZE_BYTES = 10 * 1024   # 10 KB — rejects blank/black frames
_MIN_ENTROPY = 0.5                 # bits per pixel (rough); 0 = solid colour


def _image_entropy(image_path: str) -> float:
    """Estimate Shannon entropy of the image's pixel values (grayscale).

    Returns a float in [0, 8] where 0 = solid colour and 8 = maximum variety.
    Falls back to 0.0 if image libs are unavailable.
    """
    try:
        # Use stdlib only — PIL is optional
        import struct
        import zlib

        data = Path(image_path).read_bytes()
        # Compress the raw bytes; high compression ratio → low entropy
        compressed_len = len(zlib.compress(data, level=9))
        raw_len = len(data)
        if raw_len == 0:
            return 0.0
        ratio = compressed_len / raw_len
        # Map ratio to [0, 8]: ratio ~1.0 → high entropy; ratio ~0.01 → low entropy
        return min(8.0, max(0.0, 8.0 * ratio))
    except Exception:
        return 0.0


class VeritasPipeline:
    """Orchestrate the Veritas validation loop for a single USD stage.

    Args:
        auditor: UsdAuditor implementation (required).
        renderer: Renderer implementation (required).
        vision: Optional VisionBackend for LLM scene cross-check.
        segmentor: Optional Segmentor for mask-based validation.
        sim_validator: Optional SimValidator (Isaac Sim / Mission Control).
        output_dir: Directory where rendered images and reports are written.
    """

    def __init__(
        self,
        auditor: UsdAuditor,
        renderer: Renderer,
        vision: VisionBackend | None = None,
        segmentor: Segmentor | None = None,
        sim_validator: SimValidator | None = None,
        output_dir: str = "./veritas_out",
    ) -> None:
        self._auditor = auditor
        self._renderer = renderer
        self._vision = vision
        self._segmentor = segmentor
        self._sim_validator = sim_validator
        self._output_dir = Path(output_dir)

    def run(self, stage_path: str) -> VeritasReport:
        """Run the full validation loop for *stage_path*.

        Steps:
          1. USD audit (always)
          2. Render (always)
          3. Render validity check — size > 10 KB and entropy > 0.5
          4. Segmentation (if segmentor configured)
          5. Vision cross-check (if vision backend configured)
          6. Build and return VeritasReport

        Args:
            stage_path: Absolute or relative path to the USD stage.

        Returns:
            VeritasReport with verdict PASS, WARN, or FAIL and a reason string.
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)

        # ------------------------------------------------------------------
        # Step 1: USD audit
        # ------------------------------------------------------------------
        audit_result = self._auditor.audit(stage_path)

        # ------------------------------------------------------------------
        # Step 2: Render
        # ------------------------------------------------------------------
        stage_stem = Path(stage_path).stem
        render_path = str(self._output_dir / f"{stage_stem}_render.png")
        render_result = self._renderer.render(stage_path, render_path)

        # ------------------------------------------------------------------
        # Step 3: Render validity check
        # ------------------------------------------------------------------
        if render_result.file_size_bytes <= _MIN_FILE_SIZE_BYTES:
            return VeritasReport(
                usd_audit=audit_result,
                render=render_result,
                verdict=Verdict.FAIL,
                reason=(
                    f"Render output is too small ({render_result.file_size_bytes} bytes "
                    f"<= {_MIN_FILE_SIZE_BYTES} bytes threshold) — likely a black frame."
                ),
            )

        if render_result.entropy <= _MIN_ENTROPY:
            return VeritasReport(
                usd_audit=audit_result,
                render=render_result,
                verdict=Verdict.FAIL,
                reason=(
                    f"Render entropy is too low ({render_result.entropy:.3f} "
                    f"<= {_MIN_ENTROPY} threshold) — image appears to be a solid colour."
                ),
            )

        # ------------------------------------------------------------------
        # Step 4: Segmentation (optional)
        # ------------------------------------------------------------------
        segment_result = None
        if self._segmentor is not None:
            segment_result = self._segmentor.segment(render_result.image_path)

        # ------------------------------------------------------------------
        # Step 5: Vision cross-check (optional)
        # ------------------------------------------------------------------
        vision_result = None
        if self._vision is not None:
            vision_result = self._vision.describe(
                render_result.image_path,
                context=f"USD stage: {stage_path}",
            )

        # ------------------------------------------------------------------
        # Step 6: Build verdict
        # ------------------------------------------------------------------
        verdict, reason = self._build_verdict(audit_result, render_result, vision_result)

        return VeritasReport(
            usd_audit=audit_result,
            render=render_result,
            vision=vision_result,
            segmentation=segment_result,
            verdict=verdict,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_verdict(
        self,
        audit_result,
        render_result: RenderResult,
        vision_result,
    ) -> tuple[Verdict, str]:
        """Determine the overall verdict from collected results."""
        issues: list[str] = []

        if audit_result.schema_violations:
            issues.append(
                f"{len(audit_result.schema_violations)} USD schema violation(s): "
                + "; ".join(audit_result.schema_violations[:3])
                + ("..." if len(audit_result.schema_violations) > 3 else "")
            )

        if not render_result.valid:
            issues.append("Renderer flagged the output as invalid.")

        if issues:
            return Verdict.WARN, " | ".join(issues)

        reason = (
            f"Render valid ({render_result.file_size_bytes} bytes, "
            f"entropy={render_result.entropy:.3f}); "
            f"{audit_result.prim_count} prims audited with "
            f"{len(audit_result.schema_violations)} violations."
        )
        if vision_result:
            reason += f" Vision: {vision_result.description[:120]}"

        return Verdict.PASS, reason
