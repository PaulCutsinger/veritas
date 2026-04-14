"""
veritas.impl.usd.prim_auditor
------------------------------
Concrete UsdAuditor that walks a USD stage using pxr.Usd, collects prim
metadata, and checks for common SimReady violations.
"""
from __future__ import annotations

import sys

try:
    from pxr import Usd, UsdGeom, UsdPhysics, Sdf
    _HAS_PXR = True
except ImportError:
    _HAS_PXR = False

from ...core.models import PrimInfo, UsdAuditResult
from ...interface.usd_auditor import UsdAuditor

# Sentinel transform used when xformOp data is unavailable
_IDENTITY_XFORM: list[float] = [
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
]


def _get_world_transform(prim: "Usd.Prim") -> list[float]:
    """Return the 4x4 world-space transform as a flat 16-float list.

    Falls back to identity if the prim is not an Xformable.
    """
    if not prim.IsA(UsdGeom.Xformable):
        return _IDENTITY_XFORM[:]

    xformable = UsdGeom.Xformable(prim)
    try:
        time = Usd.TimeCode.Default()
        mat = xformable.ComputeLocalToWorldTransform(time)
        return [mat[row][col] for row in range(4) for col in range(4)]
    except Exception:
        return _IDENTITY_XFORM[:]


def _is_robot_prim(prim: "Usd.Prim") -> bool:
    name = prim.GetName()
    return "robot" in name.lower()


def _has_physics_schema(prim: "Usd.Prim") -> bool:
    return prim.HasAPI(UsdPhysics.ArticulationRootAPI) or prim.HasAPI(
        UsdPhysics.RigidBodyAPI
    )


def _has_semantics_label(prim: "Usd.Prim") -> bool:
    """Check for a 'semantics:labels' attribute (Isaac Sim / Replicator convention)."""
    for attr in prim.GetAttributes():
        ns = attr.GetNamespace()
        if ns in ("semantics", "semantic"):
            return True
    return False


class PrimAuditor(UsdAuditor):
    """Walk every prim on a USD stage and report SimReady compliance issues."""

    def audit(self, stage_path: str) -> UsdAuditResult:
        if not _HAS_PXR:
            raise ImportError(
                "pxr (USD Python bindings) is not installed or not on sys.path. "
                "Install via `pip install usd-core` or source the Isaac Sim Python environment."
            )

        stage = Usd.Stage.Open(stage_path)
        if not stage:
            raise RuntimeError(f"Failed to open USD stage: {stage_path}")

        prims: list[PrimInfo] = []
        violations: list[str] = []

        for prim in stage.Traverse():
            if not prim.IsValid():
                continue

            prim_path = str(prim.GetPath())
            prim_type = prim.GetTypeName() or "Unknown"
            transform = _get_world_transform(prim)

            prims.append(PrimInfo(path=prim_path, type=prim_type, transform=transform))

            # SimReady check 1: robot Xforms must carry a physics articulation schema.
            if _is_robot_prim(prim) and prim.IsA(UsdGeom.Xform):
                if not _has_physics_schema(prim):
                    violations.append(
                        f"{prim_path}: robot Xform is missing UsdPhysics "
                        "ArticulationRootAPI or RigidBodyAPI"
                    )

            # SimReady check 2: every Xform prim should have a semantics label.
            if prim.IsA(UsdGeom.Xform) and not _has_semantics_label(prim):
                violations.append(
                    f"{prim_path}: Xform prim has no semantics label "
                    "(add 'semantics:labels' attribute)"
                )

        return UsdAuditResult(
            stage_path=stage_path,
            prim_count=len(prims),
            prims=prims,
            schema_violations=violations,
        )
