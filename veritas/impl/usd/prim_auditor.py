"""
veritas.impl.usd.prim_auditor
------------------------------
Concrete UsdAuditor that walks a USD stage using pxr.Usd, collects prim
metadata, and checks for SimReady and USD compliance violations.

Two layers of checks:
  1. UsdUtils.ComplianceChecker — Pixar's built-in USD compliance rules
     (missing default prim, broken references, USDZ packaging issues, etc.)
  2. SimReady checks — factory-sim specific: physics schemas, semantics labels
"""

from __future__ import annotations

try:
    from pxr import Usd, UsdGeom, UsdPhysics, UsdUtils

    _HAS_PXR = True
except ImportError:
    _HAS_PXR = False

from ...core.models import PrimInfo, UsdAuditResult
from ...interface.usd_auditor import UsdAuditor

# Sentinel transform used when xformOp data is unavailable
_IDENTITY_XFORM: list[float] = [
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
]


def _get_world_transform(prim: Usd.Prim) -> list[float]:
    """Return the 4x4 world-space transform as a flat 16-float list."""
    if not prim.IsA(UsdGeom.Xformable):
        return _IDENTITY_XFORM[:]
    xformable = UsdGeom.Xformable(prim)
    try:
        mat = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        return [mat[row][col] for row in range(4) for col in range(4)]
    except Exception:
        return _IDENTITY_XFORM[:]


def _is_robot_prim(prim: Usd.Prim) -> bool:
    return "robot" in prim.GetName().lower()


def _has_physics_schema(prim: Usd.Prim) -> bool:
    return prim.HasAPI(UsdPhysics.ArticulationRootAPI) or prim.HasAPI(UsdPhysics.RigidBodyAPI)


def _has_semantics_label(prim: Usd.Prim) -> bool:
    """Check for semantics:labels attribute (Isaac Sim / Replicator convention)."""
    for attr in prim.GetAttributes():
        ns = attr.GetNamespace()
        if ns in ("semantics", "semantic"):
            return True
    return False


def _run_compliance_checker(stage_path: str) -> list[str]:
    """Run UsdUtils.ComplianceChecker and return all errors and warnings as strings.

    ComplianceChecker is the authoritative USD compliance tool (same rules as
    the usdchecker CLI). It catches: missing default prim, broken sublayer/
    reference paths, invalid attribute types, USDZ packaging violations, etc.
    """
    checker = UsdUtils.ComplianceChecker(
        arkit=False,
        skipARKitRootLayerCheck=True,
        rootPackageOnly=False,
        skipVariants=False,
        verbose=False,
    )
    checker.CheckCompliance(stage_path)

    violations: list[str] = []
    for err in checker.GetErrors():
        violations.append(f"[compliance:error] {err}")
    for warn in checker.GetWarnings():
        violations.append(f"[compliance:warn] {warn}")
    for fail in checker.GetFailedChecks():
        violations.append(f"[compliance:fail] {fail}")
    return violations


class PrimAuditor(UsdAuditor):
    """Walk every prim on a USD stage and report compliance + SimReady issues.

    Args:
        run_compliance: Whether to run UsdUtils.ComplianceChecker (default True).
            Disable in environments where the checker produces false positives
            (e.g. stages with Omniverse-specific extensions).
        check_semantics: Whether to warn on Xform prims missing semantics labels.
    """

    def __init__(self, run_compliance: bool = True, check_semantics: bool = True) -> None:
        self._run_compliance = run_compliance
        self._check_semantics = check_semantics

    def audit(self, stage_path: str) -> UsdAuditResult:
        if not _HAS_PXR:
            raise ImportError(
                "pxr (USD Python bindings) is not installed. "
                "Install via `pip install usd-core` or source the Isaac Sim Python environment."
            )

        stage = Usd.Stage.Open(stage_path)
        if not stage:
            raise RuntimeError(f"Failed to open USD stage: {stage_path}")

        prims: list[PrimInfo] = []
        violations: list[str] = []

        # --- Layer 1: UsdUtils.ComplianceChecker ---
        if self._run_compliance:
            violations.extend(_run_compliance_checker(stage_path))

        # --- Layer 2: Walk prims for SimReady checks ---
        for prim in stage.Traverse():
            if not prim.IsValid():
                continue

            prim_path = str(prim.GetPath())
            prim_type = prim.GetTypeName() or "Unknown"
            transform = _get_world_transform(prim)
            prims.append(PrimInfo(path=prim_path, type=prim_type, transform=transform))

            if _is_robot_prim(prim) and prim.IsA(UsdGeom.Xform):
                if not _has_physics_schema(prim):
                    violations.append(
                        f"[simready:physics] {prim_path}: robot Xform is missing "
                        "UsdPhysics ArticulationRootAPI or RigidBodyAPI"
                    )

            if self._check_semantics and prim.IsA(UsdGeom.Xform) and not _has_semantics_label(prim):
                violations.append(
                    f"[simready:semantics] {prim_path}: Xform prim has no semantics label"
                )

        return UsdAuditResult(
            stage_path=stage_path,
            prim_count=len(prims),
            prims=prims,
            schema_violations=violations,
        )
