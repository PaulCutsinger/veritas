"""
tests/test_spatial_auditor.py
------------------------------
Integration tests for ReachabilityAuditor and ClashAuditor using real demo scenes.
Skipped if pxr not installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pxr", reason="usd-core not installed")

from veritas.impl.usd.spatial_auditor import run_spatial_audits

SCENE_DIR = Path(__file__).parent.parent / "scene" / "usd"
DEMO4 = SCENE_DIR / "demo4_robot_pick_place.usda"
DEMO5 = SCENE_DIR / "demo5_robot_conveyor_clash.usda"


def _require_scene(path: Path) -> None:
    if not path.exists():
        pytest.skip(
            f"Demo scene not built: {path.name} — run: python3 -m veritas.scene_builder.demo_scenes"
        )


class TestReachabilityAuditorDemo4:
    def setup_method(self):
        _require_scene(DEMO4)

    def test_finds_robot(self):
        result = run_spatial_audits(str(DEMO4))
        assert result["reachability"]["robot_path"] == "/World/Robot"

    def test_reach_radius_correct(self):
        result = run_spatial_audits(str(DEMO4))
        assert abs(result["reachability"]["reach_radius_m"] - 1.249) < 0.001

    def test_both_zones_found(self):
        result = run_spatial_audits(str(DEMO4))
        zones = result["reachability"]["zones"]
        zone_types = {z["zone_type"] for z in zones}
        assert "pick" in zone_types
        assert "place" in zone_types

    def test_pick_zone_reachable(self):
        result = run_spatial_audits(str(DEMO4))
        pick = next(z for z in result["reachability"]["zones"] if z["zone_type"] == "pick")
        assert pick["reachable"] is True
        assert pick["distance_m"] < 1.249

    def test_place_zone_reachable(self):
        result = run_spatial_audits(str(DEMO4))
        place = next(z for z in result["reachability"]["zones"] if z["zone_type"] == "place")
        assert place["reachable"] is True
        assert place["distance_m"] < 1.249

    def test_no_violations_when_reachable(self):
        result = run_spatial_audits(str(DEMO4))
        reach_violations = [v for v in result["all_violations"] if "[reach:unreachable]" in v]
        assert reach_violations == []

    def test_zone_distance_plausible(self):
        """Zone centroids should be 0.5–1.2 m from robot base."""
        result = run_spatial_audits(str(DEMO4))
        for zone in result["reachability"]["zones"]:
            assert 0.1 < zone["distance_m"] < 1.249


class TestClashAuditorDemo5:
    def setup_method(self):
        _require_scene(DEMO5)

    def test_detects_clash(self):
        result = run_spatial_audits(str(DEMO5))
        assert len(result["clash"]["clashes"]) >= 1

    def test_clash_is_critical(self):
        result = run_spatial_audits(str(DEMO5))
        clashes = result["clash"]["clashes"]
        severities = {c["severity"] for c in clashes}
        assert "critical" in severities

    def test_clash_overlap_positive(self):
        result = run_spatial_audits(str(DEMO5))
        for clash in result["clash"]["clashes"]:
            assert clash["overlap_m"] > 0.0

    def test_clash_overlap_exceeds_critical_threshold(self):
        """Critical severity requires overlap > 0.3 m."""
        result = run_spatial_audits(str(DEMO5))
        critical = [c for c in result["clash"]["clashes"] if c["severity"] == "critical"]
        assert all(c["overlap_m"] > 0.3 for c in critical)

    def test_clash_target_is_conveyor(self):
        result = run_spatial_audits(str(DEMO5))
        targets = {c["target_path"] for c in result["clash"]["clashes"]}
        assert "/World/Conveyor" in targets

    def test_clash_violation_string_format(self):
        result = run_spatial_audits(str(DEMO5))
        for v in result["clash"]["violations"]:
            assert v.startswith("[clash:")
            assert "overlap" in v

    def test_violation_count(self):
        result = run_spatial_audits(str(DEMO5))
        assert len(result["all_violations"]) >= 1


class TestSceneBuilderRoundtrip:
    """Build scenes and immediately audit them."""

    def test_all_demo_scenes_have_prims(self):
        from veritas.impl.usd.prim_auditor import PrimAuditor

        auditor = PrimAuditor(run_compliance=False, check_semantics=False)
        for scene_file in sorted(SCENE_DIR.glob("demo*.usda")):
            result = auditor.audit(str(scene_file))
            assert result.prim_count > 5, f"{scene_file.name}: too few prims ({result.prim_count})"

    def test_demo1_has_boxes(self):
        from veritas.impl.usd.prim_auditor import PrimAuditor

        auditor = PrimAuditor(run_compliance=False, check_semantics=False)
        result = auditor.audit(str(SCENE_DIR / "demo1_shelf_boxes.usda"))
        box_prims = [p for p in result.prims if "Box" in p.path]
        assert len(box_prims) >= 12

    def test_demo2_has_robot_with_articulation(self):
        from pxr import Usd, UsdPhysics

        stage = Usd.Stage.Open(str(SCENE_DIR / "demo2_robot_table.usda"))
        robot = stage.GetPrimAtPath("/World/Robot")
        assert robot.IsValid()
        assert robot.HasAPI(UsdPhysics.ArticulationRootAPI)

    def test_demo3_conveyor_has_belt_speed(self):
        from pxr import Usd

        stage = Usd.Stage.Open(str(SCENE_DIR / "demo3_conveyor_physics.usda"))
        conveyor = stage.GetPrimAtPath("/World/Conveyor")
        attr = conveyor.GetAttribute("conveyor:belt_speed_mps")
        assert attr.IsValid()
        assert attr.Get() == pytest.approx(0.3, abs=0.01)

    def test_demo3_boxes_have_physics(self):
        from pxr import Usd, UsdPhysics

        stage = Usd.Stage.Open(str(SCENE_DIR / "demo3_conveyor_physics.usda"))
        for i in range(3):
            box = stage.GetPrimAtPath(f"/World/Box_{i:02d}")
            assert box.IsValid()
            assert box.HasAPI(UsdPhysics.RigidBodyAPI)

    def test_demo5_no_compliance_errors(self):
        from veritas.impl.usd.prim_auditor import PrimAuditor

        auditor = PrimAuditor(run_compliance=True, check_semantics=False)
        result = auditor.audit(str(SCENE_DIR / "demo5_robot_conveyor_clash.usda"))
        errors = [v for v in result.schema_violations if "[compliance:error]" in v]
        assert errors == [], f"Compliance errors: {errors}"
