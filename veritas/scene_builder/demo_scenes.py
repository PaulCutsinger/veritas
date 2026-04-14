"""
veritas.scene_builder.demo_scenes
-----------------------------------
Build the 5 veritas demo USD stages. Each function returns the path to the
written .usda file.

Run standalone:
    python3 -m veritas.scene_builder.demo_scenes --out-dir ./scene/usd
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

from .factory_prims import (
    add_box,
    add_conveyor,
    add_default_lighting,
    add_floor,
    add_robot_arm,
    add_shelf,
    add_table,
    add_zone,
)


def _new_stage(out_path: str) -> Usd.Stage:
    stage = Usd.Stage.CreateNew(out_path)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    stage.SetMetadata("metersPerUnit", 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())

    # Physics scene
    phys_scene = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
    phys_scene.GetGravityDirectionAttr().Set(Gf.Vec3f(0, -1, 0))
    phys_scene.GetGravityMagnitudeAttr().Set(9.81)

    return stage


# ---------------------------------------------------------------------------
# Demo 1: Shelf with boxes
# ---------------------------------------------------------------------------


def build_shelf_with_boxes(out_path: str) -> str:
    """
    A 4-shelf industrial unit with 12 cardboard boxes distributed across shelves.
    Validates: USD compliance, SimReady physics, semantics labels.
    """
    stage = _new_stage(out_path)
    add_default_lighting(stage)
    add_floor(stage, size=8.0)

    add_shelf(
        stage,
        path="/World/Shelf_A",
        position=(0, 0, 0),
        width=2.2,
        depth=0.55,
        height=2.4,
        num_shelves=4,
    )

    # Shelf boards at y = 0, 0.6, 1.2, 1.8, 2.4 (height=2.4, num_shelves=4).
    # Board half-thickness = panel_t/2 = 0.015 m → top surface = board_y + 0.015.
    # Box half-size = 0.11 m → box centre = board_top + 0.11 = board_y + 0.125.
    # kinematic=True: boxes are display props; skip physics so they don't fall during warmup.
    shelf_board_y = [i * (2.4 / 4) for i in range(4)]  # [0.0, 0.6, 1.2, 1.8]
    box_colours = [
        (0.8, 0.4, 0.1),  # cardboard orange
        (0.2, 0.5, 0.8),  # blue
        (0.85, 0.75, 0.1),  # yellow
        (0.6, 0.2, 0.7),  # purple
    ]

    box_idx = 0
    for row, board_y in enumerate(shelf_board_y):
        box_y = board_y + 0.015 + 0.11  # board top + box half-height
        for col in range(3):
            x = (col - 1) * 0.6
            colour = box_colours[row % len(box_colours)]
            add_box(
                stage,
                path=f"/World/Box_{box_idx:02d}",
                size=0.22,
                position=(x, box_y, 0.0),
                colour=colour,
                kinematic=True,
                label="cardboard_box",
            )
            box_idx += 1

    stage.Save()
    return out_path


# ---------------------------------------------------------------------------
# Demo 2: Robot on a table
# ---------------------------------------------------------------------------


def build_robot_on_table(out_path: str) -> str:
    """
    FANUC CRX-10iA/L simplified arm mounted on a work table.
    Robot pose: mid-reach picking position.
    Validates: ArticulationRootAPI, robot physics schema, reach envelope.
    """
    stage = _new_stage(out_path)
    add_default_lighting(stage)
    add_floor(stage, size=8.0)

    add_table(
        stage,
        path="/World/WorkTable",
        position=(0, 0, 0),
        width=1.6,
        depth=0.9,
        height=0.75,
    )

    # Robot base sits on the table surface (y=0.75)
    robot_prim, reach = add_robot_arm(
        stage,
        path="/World/Robot",
        base_position=(0.0, 0.75, 0.0),
        max_reach_m=1.249,
    )

    # Small part tray on table next to robot
    add_box(
        stage,
        path="/World/PartTray",
        size=0.08,
        position=(0.55, 0.79, 0.25),
        colour=(0.9, 0.9, 0.9),
        label="part_tray",
    )

    stage.Save()
    return out_path


# ---------------------------------------------------------------------------
# Demo 3: Box moving on conveyor (physics)
# ---------------------------------------------------------------------------


def build_conveyor_physics(out_path: str) -> str:
    """
    A conveyor belt with 3 cardboard boxes.
    Belt is kinematic; boxes have full rigid-body physics.
    In Isaac Sim, surface velocity drives boxes along the belt.
    Validates: conveyor physics setup, box rigid bodies, belt velocity metadata.
    """
    stage = _new_stage(out_path)
    add_default_lighting(stage)
    add_floor(stage, size=10.0)

    add_conveyor(
        stage,
        path="/World/Conveyor",
        position=(0, 0, 0),
        length=4.0,
        width=0.6,
        height=0.85,
        belt_speed_mps=0.3,
    )

    # Three boxes sitting on belt surface. Belt top = height + belt_t = 0.85 + 0.01 = 0.86 m.
    # Box half = 0.11 m → box centre = 0.86 + 0.11 = 0.97 m.
    # kinematic=True for render; set to False for physics simulation in Isaac Sim.
    belt_surface_y = 0.85 + 0.01 + 0.11  # 0.97 m
    for i, z_pos in enumerate([-1.2, 0.0, 1.2]):
        add_box(
            stage,
            path=f"/World/Box_{i:02d}",
            size=0.22,
            position=(0, belt_surface_y, z_pos),
            colour=(0.8, 0.4, 0.1),
            kinematic=True,
            label="conveyor_box",
        )

    stage.Save()
    return out_path


# ---------------------------------------------------------------------------
# Demo 4: Robot with pick zone + place zone (reachability)
# ---------------------------------------------------------------------------


def build_robot_pick_place(out_path: str) -> str:
    """
    Robot with explicitly defined pick and place zones.
    Both zones are positioned within the robot's rated reach (1.249 m).
    Veritas spatial auditor checks: zone centroid distance from robot base < reach.
    """
    stage = _new_stage(out_path)
    add_default_lighting(stage)
    add_floor(stage, size=8.0)

    add_table(stage, path="/World/WorkTable", position=(0, 0, 0), width=1.6, depth=0.9, height=0.75)

    robot_prim, reach = add_robot_arm(
        stage,
        path="/World/Robot",
        base_position=(0.0, 0.75, 0.0),
        max_reach_m=1.249,
    )

    # Pick zone: 0.6 m in front of robot, on table surface
    # Distance from robot base = sqrt(0.6² + 0.0² + 0.4²) ≈ 0.72 m < 1.249 — REACHABLE
    add_zone(
        stage,
        path="/World/PickZone",
        position=(0.6, 0.75, 0.4),
        radius=0.12,
        colour=(0.1, 0.9, 0.1),
        label="pick_zone",
        zone_type="pick",
    )

    # Place zone: 0.5 m to the side, slightly lower
    # Distance ≈ sqrt(0.5² + 0.15² + 0.6²) ≈ 0.80 m < 1.249 — REACHABLE
    add_zone(
        stage,
        path="/World/PlaceZone",
        position=(-0.5, 0.60, 0.6),
        radius=0.12,
        colour=(0.9, 0.1, 0.1),
        label="place_zone",
        zone_type="place",
    )

    # Annotate robot with pick/place metadata for veritas
    robot_prim.CreateAttribute("veritas:pick_zone_path", Sdf.ValueTypeNames.String).Set(
        "/World/PickZone"
    )
    robot_prim.CreateAttribute("veritas:place_zone_path", Sdf.ValueTypeNames.String).Set(
        "/World/PlaceZone"
    )

    # The box to pick
    add_box(
        stage,
        path="/World/PickBox",
        size=0.12,
        position=(0.6, 0.81, 0.4),
        colour=(0.8, 0.4, 0.1),
        label="pick_target",
    )

    stage.Save()
    return out_path


# ---------------------------------------------------------------------------
# Demo 5: Robot + conveyor with clash detection
# ---------------------------------------------------------------------------


def build_robot_conveyor_clash(out_path: str) -> str:
    """
    A robot arm mounted on a table next to a conveyor belt.
    The robot's reach envelope overlaps the conveyor's bounding box —
    veritas spatial auditor detects this and emits a clash alert.

    Layout (top-down, X-Z plane):
        [Table+Robot] at X=-1.2   [Conveyor] at X=0.5
        Robot reach radius = 1.249 m
        Nearest conveyor edge = 0.5 - 0.3 = 0.2 m from origin → robot can reach it.
        Overlap = 1.249 - (0.5 - 0.3 - 1.2) ... see clash auditor for exact computation.
    """
    stage = _new_stage(out_path)
    add_default_lighting(stage)
    add_floor(stage, size=10.0)

    # Table + robot on the left.
    # Robot base at X=-0.65. Conveyor nearest edge at X=0.2 (centre 0.5, half-width 0.3).
    # Gap = 0.2 - (-0.65) = 0.85 m < reach 1.249 m → overlap = 0.399 m → CRITICAL.
    add_table(
        stage,
        path="/World/WorkTable",
        position=(-0.65, 0, 0),
        width=1.4,
        depth=0.8,
        height=0.75,
    )
    robot_prim, reach = add_robot_arm(
        stage,
        path="/World/Robot",
        base_position=(-0.65, 0.75, 0.0),
        max_reach_m=1.249,
    )

    # Conveyor to the right — width=0.6 → spans X=[0.2, 0.8], nearest edge X=0.2
    # Gap from robot base (-0.8) to nearest edge (0.2) = 1.0 m < 1.249 m → CRITICAL
    add_conveyor(
        stage,
        path="/World/Conveyor",
        position=(0.5, 0, 0),
        length=3.5,
        width=0.6,
        height=0.85,
        belt_speed_mps=0.4,
    )

    # Boxes on conveyor
    belt_y = 0.85 + 0.01 + 0.12
    for i, z in enumerate([-0.8, 0.4]):
        add_box(
            stage,
            path=f"/World/Box_{i:02d}",
            size=0.22,
            position=(0.5, belt_y, z),
            colour=(0.8, 0.4, 0.1),
            label="conveyor_box",
        )

    # Annotate robot with clash check targets
    robot_prim.CreateAttribute("veritas:clash_check_targets", Sdf.ValueTypeNames.StringArray).Set(
        ["/World/Conveyor"]
    )

    stage.Save()
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


ALL_BUILDERS = {
    "shelf_boxes": (build_shelf_with_boxes, "demo1_shelf_boxes.usda"),
    "robot_table": (build_robot_on_table, "demo2_robot_table.usda"),
    "conveyor_physics": (build_conveyor_physics, "demo3_conveyor_physics.usda"),
    "robot_pick_place": (build_robot_pick_place, "demo4_robot_pick_place.usda"),
    "robot_conveyor_clash": (build_robot_conveyor_clash, "demo5_robot_conveyor_clash.usda"),
}


def build_all(out_dir: str = "./scene/usd") -> dict[str, str]:
    """Build all demo scenes. Returns {name: path} dict."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, (builder, filename) in ALL_BUILDERS.items():
        p = str(out / filename)
        print(f"Building {name} → {p}")
        builder(p)
        print(f"  ✓ saved ({Path(p).stat().st_size // 1024} KB)")
        paths[name] = p
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build veritas demo USD scenes")
    parser.add_argument("--out-dir", default="./scene/usd", help="Output directory")
    parser.add_argument("--scene", choices=list(ALL_BUILDERS.keys()), help="Build one scene only")
    args = parser.parse_args()

    if args.scene:
        builder, filename = ALL_BUILDERS[args.scene]
        out_path = str(Path(args.out_dir) / filename)
        Path(args.out_dir).mkdir(parents=True, exist_ok=True)
        builder(out_path)
        print(f"Saved: {out_path}")
    else:
        build_all(args.out_dir)
