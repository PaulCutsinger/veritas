"""
veritas.impl.isaac.isaac_renderer
------------------------------------
Concrete Renderer using Isaac Sim SimulationApp (headless RTX).
Must be called from within an active Isaac Sim Python environment.
"""

from __future__ import annotations

import time
from pathlib import Path

from ...core.models import RenderResult
from ...interface.renderer import Renderer


class IsaacSimRenderer(Renderer):
    """
    Render a USD stage via Isaac Sim (headless RTX).

    Assumes SimulationApp is already running (call from render_demos.py).
    Args:
        warmup_frames: Render warmup frames after stage load.
        width / height: Viewport resolution.
        camera_preset: "iso" | "front" | "topdown"
    """

    CAMERAS = {
        "iso": {"eye": (-4, 3.5, -4), "at": (0, 1, 0), "focal_mm": 28.0, "warmup": 80},
        "front": {"eye": (0, 2.0, 5), "at": (0, 1, 0), "focal_mm": 35.0, "warmup": 60},
        "topdown": {"eye": (0, 7, 0), "at": (0, 0, 0), "focal_mm": 50.0, "warmup": 60},
        # Scene-specific presets
        "shelf": {"eye": (-3, 2.5, 4), "at": (0, 1.2, 0), "focal_mm": 35.0, "warmup": 80},
        "conveyor": {"eye": (2, 2.5, 4), "at": (0, 0.9, 0), "focal_mm": 28.0, "warmup": 80},
        "clash": {"eye": (-4, 3.5, 5), "at": (-0.3, 1, 0), "focal_mm": 28.0, "warmup": 80},
    }

    def __init__(
        self,
        warmup_frames: int = 80,
        width: int = 1280,
        height: int = 720,
        camera_preset: str = "iso",
    ) -> None:
        self._warmup = warmup_frames
        self._width = width
        self._height = height
        self._camera_preset = camera_preset

    def render(self, stage_path: str, output_path: str) -> RenderResult:
        try:
            import omni.kit.viewport.utility
            import omni.renderer_capture
            import omni.usd
            from isaacsim.core.api import World
            from pxr import Gf, UsdGeom, UsdLux  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                f"IsaacSimRenderer requires an active Isaac Sim environment: {e}"
            ) from e

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        omni.usd.get_context().open_stage(str(stage_path))
        _app_update(60)

        stage = omni.usd.get_context().get_stage()
        _ensure_lighting(stage)

        world = World()
        world.reset()
        _app_update(20)

        preset = self.CAMERAS.get(self._camera_preset, self.CAMERAS["iso"])
        cam_path = "/VeritasCamera"
        _place_camera(stage, cam_path, preset["eye"], preset["at"], preset["focal_mm"])

        viewport = omni.kit.viewport.utility.get_active_viewport()
        viewport.set_active_camera(cam_path)
        viewport.set_texture_resolution((self._width, self._height))

        for _ in range(preset.get("warmup", self._warmup)):
            world.step(render=True)

        cap = omni.renderer_capture.acquire_renderer_capture_interface()
        cap.capture_next_frame_swapchain(output_path)
        for _ in range(60):  # extra frames to flush async PNG write
            world.step(render=True)

        if not Path(output_path).exists():
            raise RuntimeError(f"Render capture failed — no file at: {output_path}")

        # Wait for file size to stabilise (async write may still be in progress)
        prev_size = -1
        for _ in range(20):
            cur_size = Path(output_path).stat().st_size
            if cur_size == prev_size and cur_size > 0:
                break
            prev_size = cur_size
            for _ in range(5):
                world.step(render=True)

        file_size = Path(output_path).stat().st_size
        from veritas.core.pipeline import _image_entropy

        entropy = _image_entropy(output_path)
        return RenderResult(
            image_path=output_path,
            file_size_bytes=file_size,
            timestamp=time.time(),
            entropy=entropy,
            valid=file_size > 10 * 1024 and entropy > 0.5,
        )


def _app_update(n: int) -> None:
    import omni.kit.app

    app = omni.kit.app.get_app()
    for _ in range(n):
        app.update()


def _ensure_lighting(stage) -> None:
    from pxr import Gf, UsdGeom, UsdLux

    has_light = any(
        prim.IsA(UsdLux.BoundableLightBase) or prim.IsA(UsdLux.NonboundableLightBase)
        for prim in stage.Traverse()
    )
    if has_light:
        return
    UsdGeom.Xform.Define(stage, "/World/Lights")
    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Dome")
    dome.GetIntensityAttr().Set(800.0)
    dome.GetColorAttr().Set(Gf.Vec3f(0.9, 0.95, 1.0))
    sun = UsdLux.DistantLight.Define(stage, "/World/Lights/Sun")
    sun.GetIntensityAttr().Set(5000.0)
    UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-55.0, 25.0, 0.0))


def _place_camera(stage, cam_path: str, eye, at, focal_mm: float) -> None:
    import numpy as np
    from pxr import Gf, UsdGeom

    eye = np.array(eye, dtype=float)
    at = np.array(at, dtype=float)
    up = np.array([0.0, 1.0, 0.0])
    fwd = at - eye
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, up)
    if np.linalg.norm(right) < 1e-6:
        up = np.array([0.0, 0.0, 1.0])
        right = np.cross(fwd, up)
    right /= np.linalg.norm(right)
    up2 = np.cross(right, fwd)
    mat = Gf.Matrix4d(
        right[0],
        right[1],
        right[2],
        0,
        up2[0],
        up2[1],
        up2[2],
        0,
        -fwd[0],
        -fwd[1],
        -fwd[2],
        0,
        eye[0],
        eye[1],
        eye[2],
        1,
    )
    cam = UsdGeom.Camera.Define(stage, cam_path)
    cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.05, 500.0))
    cam.GetFocalLengthAttr().Set(focal_mm)
    xf = UsdGeom.Xformable(cam.GetPrim())
    for op in xf.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeTransform:
            op.Set(mat)
            return
    xf.AddTransformOp().Set(mat)
