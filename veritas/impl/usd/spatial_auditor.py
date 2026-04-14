"""
veritas.impl.usd.spatial_auditor
----------------------------------
Spatial audits that complement PrimAuditor:

  1. ReachabilityAuditor — given a robot prim with a ReachEnvelope sphere and
     zone prims (pick/place), checks that every zone centroid is within reach.

  2. ClashAuditor — given a robot prim and one or more target prims (conveyors,
     walls, fixtures), checks whether the robot's reach envelope (sphere) overlaps
     the target's axis-aligned bounding box (AABB). Reports overlap volume.

Both auditors return structured dicts that are merged into UsdAuditResult
schema_violations by the caller (or can be used standalone).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

try:
    from pxr import Gf, Usd, UsdGeom

    _HAS_PXR = True
except ImportError:
    _HAS_PXR = False


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ReachResult:
    robot_path: str
    robot_base_world: tuple[float, float, float]
    reach_radius_m: float
    zones: list[dict] = field(default_factory=list)
    # Each zone dict: {path, zone_type, centroid, distance_m, reachable, margin_m}
    violations: list[str] = field(default_factory=list)


@dataclass
class ClashResult:
    robot_path: str
    robot_base_world: tuple[float, float, float]
    reach_radius_m: float
    clashes: list[dict] = field(default_factory=list)
    # Each clash dict: {target_path, overlap_m, nearest_point, severity}
    violations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _world_translate(prim: Usd.Prim) -> tuple[float, float, float]:
    """Return world-space translation of prim (in metres).

    USD matrices are row-major: translation is in row 3, columns 0-2.
    """
    xformable = UsdGeom.Xformable(prim)
    mat = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    row3 = mat.GetRow(3)
    return (row3[0], row3[1], row3[2])


def _prim_aabb(prim: Usd.Prim, stage: Usd.Stage) -> tuple[Gf.Vec3d, Gf.Vec3d] | None:
    """
    Compute axis-aligned bounding box of a prim and all its descendants.
    Returns (min_pt, max_pt) in world space, or None if no geometry found.
    """
    bbox_cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        includedPurposes=[UsdGeom.Tokens.default_, UsdGeom.Tokens.render],
        useExtentsHint=False,
    )
    bbox = bbox_cache.ComputeWorldBound(prim)
    rng = bbox.GetRange()
    if rng.IsEmpty():
        return None
    return rng.GetMin(), rng.GetMax()


def _sphere_aabb_distance(
    centre: Sequence[float],
    aabb_min: Sequence[float],
    aabb_max: Sequence[float],
) -> float:
    """
    Return the minimum distance from point *centre* to the AABB [min, max].
    Returns 0.0 if the centre is inside the AABB.
    """
    dx = max(aabb_min[0] - centre[0], 0.0, centre[0] - aabb_max[0])
    dy = max(aabb_min[1] - centre[1], 0.0, centre[1] - aabb_max[1])
    dz = max(aabb_min[2] - centre[2], 0.0, centre[2] - aabb_max[2])
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _closest_point_on_aabb(
    pt: Sequence[float],
    aabb_min: Sequence[float],
    aabb_max: Sequence[float],
) -> tuple[float, float, float]:
    return (
        max(aabb_min[0], min(pt[0], aabb_max[0])),
        max(aabb_min[1], min(pt[1], aabb_max[1])),
        max(aabb_min[2], min(pt[2], aabb_max[2])),
    )


# ---------------------------------------------------------------------------
# Reachability Auditor
# ---------------------------------------------------------------------------


class ReachabilityAuditor:
    """
    Check that robot pick/place zones are within the robot's rated reach.

    Discovery:
      - Finds robot prims by veritas:reach_radius_m attribute.
      - Finds zone prims by veritas:zone_type attribute (pick | place).
      - Optionally: reads veritas:pick_zone_path / veritas:place_zone_path from
        the robot prim for explicit zone associations.

    Adds violations tagged [reach:unreachable] or [reach:warn] to the result.
    """

    def audit(self, stage: Usd.Stage) -> ReachResult:
        # Find robot (first prim with reach_radius_m)
        robot_prim = None
        reach_radius = 0.0
        for prim in stage.Traverse():
            attr = prim.GetAttribute("veritas:reach_radius_m")
            if attr and attr.IsValid():
                robot_prim = prim.GetParent()  # envelope is child of robot xform
                reach_radius = float(attr.Get())
                break

        if robot_prim is None:
            # No robot in scene — reachability check is not applicable; not a violation.
            return ReachResult(robot_path="(none)", robot_base_world=(0, 0, 0), reach_radius_m=0.0)

        base_world = _world_translate(robot_prim)
        result = ReachResult(
            robot_path=str(robot_prim.GetPath()),
            robot_base_world=base_world,
            reach_radius_m=reach_radius,
        )

        # Find zones
        for prim in stage.Traverse():
            zone_type_attr = prim.GetAttribute("veritas:zone_type")
            if not (zone_type_attr and zone_type_attr.IsValid()):
                continue
            zone_type = zone_type_attr.Get()
            centroid = _world_translate(prim)
            dx = centroid[0] - base_world[0]
            dy = centroid[1] - base_world[1]
            dz = centroid[2] - base_world[2]
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            margin = reach_radius - dist
            reachable = dist <= reach_radius

            zone_info = {
                "path": str(prim.GetPath()),
                "zone_type": zone_type,
                "centroid": centroid,
                "distance_m": round(dist, 4),
                "reachable": reachable,
                "margin_m": round(margin, 4),
            }
            result.zones.append(zone_info)

            if not reachable:
                result.violations.append(
                    f"[reach:unreachable] {prim.GetPath()} ({zone_type}) is {dist:.3f} m from "
                    f"robot base — exceeds reach of {reach_radius:.3f} m by {-margin:.3f} m"
                )
            elif margin < 0.05:
                result.violations.append(
                    f"[reach:warn] {prim.GetPath()} ({zone_type}) is within reach but tight "
                    f"(margin={margin:.3f} m) — may fail under joint limits"
                )

        return result


# ---------------------------------------------------------------------------
# Clash Auditor
# ---------------------------------------------------------------------------


class ClashAuditor:
    """
    Detect spatial clashes between a robot's reach envelope and other scene objects.

    A "clash" = reach sphere overlaps with target prim's AABB.
    Severity:
      - CRITICAL: overlap > 0.3 m (robot definitely collides)
      - WARN:     overlap > 0.0 m (potential collision depending on pose)

    Tagged [clash:critical] or [clash:warn].
    """

    def audit(self, stage: Usd.Stage) -> ClashResult:
        # Find robot reach envelope
        robot_prim = None
        reach_radius = 0.0
        for prim in stage.Traverse():
            attr = prim.GetAttribute("veritas:reach_radius_m")
            if attr and attr.IsValid():
                robot_prim = prim.GetParent()
                reach_radius = float(attr.Get())
                break

        if robot_prim is None:
            # No robot in scene — clash check is not applicable; not a violation.
            return ClashResult(robot_path="(none)", robot_base_world=(0, 0, 0), reach_radius_m=0.0)

        base_world = _world_translate(robot_prim)
        result = ClashResult(
            robot_path=str(robot_prim.GetPath()),
            robot_base_world=base_world,
            reach_radius_m=reach_radius,
        )

        # Determine target prims to check
        target_attr = robot_prim.GetAttribute("veritas:clash_check_targets")
        if target_attr and target_attr.IsValid():
            target_paths = list(target_attr.Get())
        else:
            # Auto-discover: check all conveyors and structural prims
            target_paths = []
            for prim in stage.Traverse():
                label_attr = prim.GetAttribute("semantics:labels")
                if label_attr and label_attr.IsValid():
                    label = label_attr.Get()
                    if label in ("conveyor", "shelf_unit", "wall"):
                        target_paths.append(str(prim.GetPath()))

        for target_path in target_paths:
            target_prim = stage.GetPrimAtPath(target_path)
            if not target_prim.IsValid():
                continue

            aabb = _prim_aabb(target_prim, stage)
            if aabb is None:
                continue

            aabb_min, aabb_max = aabb
            dist = _sphere_aabb_distance(base_world, aabb_min, aabb_max)
            overlap = reach_radius - dist  # positive = overlap

            if overlap > 0:
                nearest = _closest_point_on_aabb(base_world, aabb_min, aabb_max)
                severity = "critical" if overlap > 0.3 else "warn"
                clash_info = {
                    "target_path": target_path,
                    "overlap_m": round(overlap, 4),
                    "nearest_point": tuple(round(v, 4) for v in nearest),
                    "severity": severity,
                }
                result.clashes.append(clash_info)
                result.violations.append(
                    f"[clash:{severity}] Robot reach envelope overlaps {target_path} "
                    f"by {overlap:.3f} m — nearest point {tuple(round(v, 2) for v in nearest)}"
                )

        return result


# ---------------------------------------------------------------------------
# Convenience: run both auditors and merge violations
# ---------------------------------------------------------------------------


def run_spatial_audits(stage_path: str) -> dict:
    """
    Open stage, run ReachabilityAuditor + ClashAuditor, return merged result dict.
    """
    if not _HAS_PXR:
        raise ImportError("pxr not available")

    stage = Usd.Stage.Open(stage_path)
    if not stage:
        raise RuntimeError(f"Cannot open stage: {stage_path}")

    reach = ReachabilityAuditor().audit(stage)
    clash = ClashAuditor().audit(stage)

    return {
        "stage_path": stage_path,
        "reachability": {
            "robot_path": reach.robot_path,
            "robot_base_world": reach.robot_base_world,
            "reach_radius_m": reach.reach_radius_m,
            "zones": reach.zones,
            "violations": reach.violations,
        },
        "clash": {
            "robot_path": clash.robot_path,
            "reach_radius_m": clash.reach_radius_m,
            "clashes": clash.clashes,
            "violations": clash.violations,
        },
        "all_violations": reach.violations + clash.violations,
    }
