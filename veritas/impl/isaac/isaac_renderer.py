"""
veritas.impl.isaac.isaac_renderer
-----------------------------------
Concrete Renderer that captures a viewport screenshot from Isaac Sim.

This stub must be executed inside an Isaac Sim Python environment where
``omni.isaac.core`` and ``omni.kit.viewport`` are available. It is intentionally
NOT imported at module level in the CLI — instantiate it only inside an Isaac Sim
script session.
"""

from __future__ import annotations

from ...core.models import RenderResult
from ...interface.renderer import Renderer


class IsaacSimRenderer(Renderer):
    """Render a USD stage by loading it in Isaac Sim and capturing the viewport.

    Args:
        resolution: (width, height) tuple for the rendered image.
        camera_prim_path: USD path to the camera prim to use for rendering.
            If None, the active viewport camera is used.
        render_frames: Number of physics/render frames to step before capture,
            allowing the scene to settle.
    """

    def __init__(
        self,
        resolution: tuple[int, int] = (1920, 1080),
        camera_prim_path: str | None = None,
        render_frames: int = 60,
    ) -> None:
        self._resolution = resolution
        self._camera_prim_path = camera_prim_path
        self._render_frames = render_frames

    def render(self, stage_path: str, output_path: str) -> RenderResult:
        """Load *stage_path* in Isaac Sim and save a screenshot to *output_path*.

        Must be called from within an Isaac Sim Python session (headless or GUI).

        Args:
            stage_path: Absolute path to the .usd or .usda file to render.
            output_path: Absolute path for the output PNG.

        Returns:
            RenderResult with file metadata and a basic validity flag.

        Raises:
            NotImplementedError: Always — this stub must be completed inside
                an Isaac Sim Python environment.
        """
        raise NotImplementedError(
            "Isaac Sim renderer: run inside an Isaac Sim Python environment. "
            "Import omni.isaac.core.World, load the stage, step render frames, "
            "then use omni.kit.capture.viewport to write the screenshot. "
            "See veritas/impl/isaac/isaac_renderer.py for the scaffold."
        )

    # ------------------------------------------------------------------
    # Helper sketch (not callable until NotImplementedError is removed)
    # ------------------------------------------------------------------
    def _capture(self, stage_path: str, output_path: str) -> RenderResult:  # noqa: D401
        """Sketch of the full implementation for reference."""
        # These imports only resolve inside Isaac Sim:
        #   from omni.isaac.core import World
        #   import omni.kit.viewport.utility as vp_util
        #   import omni.replicator.core as rep  # or omni.kit.capture.viewport
        #
        # Steps:
        #   1. world = World(); world.initialize_simulation_context()
        #   2. omni.usd.get_context().open_stage(stage_path)
        #   3. for _ in range(self._render_frames): world.step(render=True)
        #   4. vp = vp_util.get_active_viewport()
        #   5. if self._camera_prim_path: vp.set_active_camera(self._camera_prim_path)
        #   6. capture viewport frame to output_path
        #   7. compute entropy and return RenderResult
        raise NotImplementedError
