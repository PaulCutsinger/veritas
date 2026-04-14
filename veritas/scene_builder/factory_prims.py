"""
veritas.scene_builder.factory_prims
-------------------------------------
SimReady USD primitives for factory scenes.

All units: metres. Physics schemas applied per SimReady spec.
Semantics labels follow Isaac Sim Replicator convention.
"""

from __future__ import annotations

from collections.abc import Sequence

from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add_semantics(prim: Usd.Prim, label: str) -> None:
    """Add Isaac Sim Replicator semantics:labels attribute."""
    attr = prim.CreateAttribute("semantics:labels", Sdf.ValueTypeNames.String)
    attr.Set(label)


def _make_xform(stage: Usd.Stage, path: str, t: Sequence[float] = (0, 0, 0)) -> Usd.Prim:
    xf = UsdGeom.Xform.Define(stage, path)
    if any(v != 0 for v in t):
        xf.AddTranslateOp().Set(Gf.Vec3d(*t))
    return xf.GetPrim()


def _set_translate(prim: Usd.Prim, t: Sequence[float]) -> None:
    xf = UsdGeom.Xformable(prim)
    ops = xf.GetOrderedXformOps()
    for op in ops:
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            op.Set(Gf.Vec3d(*t))
            return
    xf.AddTranslateOp().Set(Gf.Vec3d(*t))


def _box_mesh(
    stage: Usd.Stage,
    path: str,
    half_extents: Sequence[float],  # (hx, hy, hz)
) -> UsdGeom.Mesh:
    """Create a box mesh (8 verts, 6 quads) at origin with given half-extents."""
    hx, hy, hz = half_extents
    pts = [
        (-hx, -hy, -hz),
        (hx, -hy, -hz),
        (hx, hy, -hz),
        (-hx, hy, -hz),
        (-hx, -hy, hz),
        (hx, -hy, hz),
        (hx, hy, hz),
        (-hx, hy, hz),
    ]
    face_counts = [4, 4, 4, 4, 4, 4]
    face_indices = [
        0,
        1,
        2,
        3,  # -Z
        4,
        5,
        6,
        7,  # +Z
        0,
        4,
        7,
        3,  # -X
        1,
        5,
        6,
        2,  # +X
        0,
        1,
        5,
        4,  # -Y
        3,
        2,
        6,
        7,  # +Y
    ]
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.GetPointsAttr().Set([Gf.Vec3f(*p) for p in pts])
    mesh.GetFaceVertexCountsAttr().Set(face_counts)
    mesh.GetFaceVertexIndicesAttr().Set(face_indices)
    mesh.GetExtentAttr().Set([Gf.Vec3f(-hx, -hy, -hz), Gf.Vec3f(hx, hy, hz)])
    return mesh


# ---------------------------------------------------------------------------
# Lighting (always call once per stage)
# ---------------------------------------------------------------------------


def add_default_lighting(stage: Usd.Stage, root: str = "/World/Lights") -> None:
    UsdGeom.Xform.Define(stage, root)
    dome = UsdLux.DomeLight.Define(stage, f"{root}/Dome")
    dome.GetIntensityAttr().Set(800.0)
    dome.GetColorAttr().Set(Gf.Vec3f(0.9, 0.95, 1.0))
    sun = UsdLux.DistantLight.Define(stage, f"{root}/Sun")
    sun.GetIntensityAttr().Set(5000.0)
    UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-55.0, 25.0, 0.0))


# ---------------------------------------------------------------------------
# Floor
# ---------------------------------------------------------------------------


def add_floor(
    stage: Usd.Stage,
    path: str = "/World/Floor",
    size: float = 10.0,
    thickness: float = 0.05,
) -> Usd.Prim:
    xf = _make_xform(stage, path, (0, -thickness, 0))
    mesh = _box_mesh(stage, f"{path}/Mesh", (size / 2, thickness / 2, size / 2))
    col = UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())  # noqa: F841
    plane = UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim())
    plane.GetApproximationAttr().Set("convexHull")
    _add_semantics(xf.GetPrim(), "floor")
    return xf.GetPrim()


# ---------------------------------------------------------------------------
# Box (rigid body)
# ---------------------------------------------------------------------------


def add_box(
    stage: Usd.Stage,
    path: str,
    size: float = 0.2,
    position: Sequence[float] = (0, 0, 0),
    colour: Sequence[float] = (0.8, 0.4, 0.1),
    kinematic: bool = False,
    label: str = "box",
) -> Usd.Prim:
    xf = UsdGeom.Xform.Define(stage, path)
    xf.AddTranslateOp().Set(Gf.Vec3d(*position))
    h = size / 2
    mesh = _box_mesh(stage, f"{path}/Mesh", (h, h, h))

    # Visual colour via displayColor
    mesh.GetDisplayColorAttr().Set([Gf.Vec3f(*colour)])

    # Physics
    UsdPhysics.RigidBodyAPI.Apply(xf.GetPrim())
    if kinematic:
        rb = UsdPhysics.RigidBodyAPI(xf.GetPrim())
        rb.GetKinematicEnabledAttr().Set(True)
    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
    col = UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim())
    col.GetApproximationAttr().Set("convexHull")
    UsdPhysics.MassAPI.Apply(xf.GetPrim()).GetMassAttr().Set(1.0)

    _add_semantics(xf.GetPrim(), label)
    return xf.GetPrim()


# ---------------------------------------------------------------------------
# Shelf unit (structural — kinematic)
# ---------------------------------------------------------------------------


def add_shelf(
    stage: Usd.Stage,
    path: str = "/World/Shelf",
    position: Sequence[float] = (0, 0, 0),
    width: float = 2.0,
    depth: float = 0.5,
    height: float = 2.2,
    num_shelves: int = 4,
    colour: Sequence[float] = (0.6, 0.55, 0.5),
) -> Usd.Prim:
    """Industrial shelf unit with upright posts and horizontal shelf boards."""
    xf = _make_xform(stage, path, position)
    _add_semantics(xf, "shelf_unit")

    hw, hd = width / 2, depth / 2
    panel_t = 0.03  # 3 cm panels
    post_t = 0.05  # 5 cm square posts

    # Four vertical posts
    for pi, (px, pz) in enumerate([(-hw, -hd), (hw, -hd), (-hw, hd), (hw, hd)]):
        pm = _box_mesh(stage, f"{path}/Post_{pi}/Mesh", (post_t / 2, height / 2, post_t / 2))
        post_xf = _make_xform(stage, f"{path}/Post_{pi}", (px, height / 2, pz))
        pm.GetDisplayColorAttr().Set([Gf.Vec3f(*colour)])
        UsdPhysics.CollisionAPI.Apply(pm.GetPrim())
        _add_semantics(post_xf, "shelf_post")

    # Shelf boards
    shelf_y_positions = [i * (height / num_shelves) for i in range(num_shelves + 1)]
    for si, sy in enumerate(shelf_y_positions):
        bm = _box_mesh(stage, f"{path}/Board_{si}/Mesh", (hw, panel_t / 2, hd))
        board_xf = _make_xform(stage, f"{path}/Board_{si}", (0, sy, 0))
        bm.GetDisplayColorAttr().Set([Gf.Vec3f(*colour)])
        UsdPhysics.CollisionAPI.Apply(bm.GetPrim())
        _add_semantics(board_xf, "shelf_board")

    return xf


# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------


def add_table(
    stage: Usd.Stage,
    path: str = "/World/Table",
    position: Sequence[float] = (0, 0, 0),
    width: float = 1.5,
    depth: float = 0.8,
    height: float = 0.75,
    colour: Sequence[float] = (0.7, 0.65, 0.55),
) -> Usd.Prim:
    xf = _make_xform(stage, path, position)
    _add_semantics(xf, "table")

    hw, hd, _hh = width / 2, depth / 2, height / 2
    top_t = 0.04
    leg_s = 0.06

    # Tabletop
    top = _box_mesh(stage, f"{path}/Top/Mesh", (hw, top_t / 2, hd))
    _make_xform(stage, f"{path}/Top", (0, height - top_t / 2, 0))
    top.GetDisplayColorAttr().Set([Gf.Vec3f(*colour)])
    UsdPhysics.CollisionAPI.Apply(top.GetPrim())
    _add_semantics(
        top.GetPrim().GetParent() if top.GetPrim().GetParent() else top.GetPrim(), "table_top"
    )

    # Legs
    leg_height = height - top_t
    for li, (lx, lz) in enumerate(
        [
            (-hw + leg_s, -hd + leg_s),
            (hw - leg_s, -hd + leg_s),
            (-hw + leg_s, hd - leg_s),
            (hw - leg_s, hd - leg_s),
        ]
    ):
        lm = _box_mesh(stage, f"{path}/Leg_{li}/Mesh", (leg_s / 2, leg_height / 2, leg_s / 2))
        _make_xform(stage, f"{path}/Leg_{li}", (lx, leg_height / 2, lz))
        lm.GetDisplayColorAttr().Set([Gf.Vec3f(*colour)])
        UsdPhysics.CollisionAPI.Apply(lm.GetPrim())

    return xf


# ---------------------------------------------------------------------------
# Robot arm (simplified FANUC CRX-10iA/L proportions)
# ---------------------------------------------------------------------------


def add_robot_arm(
    stage: Usd.Stage,
    path: str = "/World/Robot",
    base_position: Sequence[float] = (0, 0, 0),
    max_reach_m: float = 1.249,  # CRX-10iA/L rated reach
    label: str = "robot_arm",
) -> tuple[Usd.Prim, float]:
    """
    6-DOF robot arm: simplified cylinder/box geometry.
    Returns (base_prim, max_reach_m).
    """
    xf = UsdGeom.Xform.Define(stage, path)
    xf.AddTranslateOp().Set(Gf.Vec3d(*base_position))
    _add_semantics(xf.GetPrim(), label)

    # Physics articulation root
    UsdPhysics.ArticulationRootAPI.Apply(xf.GetPrim())

    robot_colour = Gf.Vec3f(0.85, 0.85, 0.85)

    def _cyl(cpath: str, radius: float, height: float) -> UsdGeom.Cylinder:
        cyl = UsdGeom.Cylinder.Define(stage, cpath)
        cyl.GetRadiusAttr().Set(radius)
        cyl.GetHeightAttr().Set(height)
        cyl.GetDisplayColorAttr().Set([robot_colour])
        return cyl

    # Base pedestal
    _make_xform(stage, f"{path}/Base", (0, 0, 0))
    base_cyl = _cyl(f"{path}/Base/Mesh", 0.12, 0.25)
    UsdGeom.Xformable(base_cyl.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(0, 0.125, 0))
    UsdPhysics.CollisionAPI.Apply(base_cyl.GetPrim())

    # Link 1 (shoulder rotate, vertical)
    _make_xform(stage, f"{path}/Link1", (0, 0.25, 0))
    l1 = _cyl(f"{path}/Link1/Mesh", 0.09, 0.18)
    UsdGeom.Xformable(l1.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(0, 0.09, 0))
    UsdPhysics.CollisionAPI.Apply(l1.GetPrim())

    # Link 2 (upper arm, tilted ~45° forward for a picking pose)
    link2_xf = UsdGeom.Xform.Define(stage, f"{path}/Link2")
    link2_xf.AddTranslateOp().Set(Gf.Vec3d(0, 0.43, 0))
    link2_xf.AddRotateXYZOp().Set(Gf.Vec3f(45, 0, 0))
    l2 = _cyl(f"{path}/Link2/Mesh", 0.07, 0.45)
    UsdGeom.Xformable(l2.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(0, 0.225, 0))
    l2.GetDisplayColorAttr().Set([robot_colour])
    UsdPhysics.CollisionAPI.Apply(l2.GetPrim())

    # Link 3 (forearm)
    link3_xf = UsdGeom.Xform.Define(stage, f"{path}/Link3")
    link3_xf.AddTranslateOp().Set(Gf.Vec3d(0, 0.45, 0.318))
    link3_xf.AddRotateXYZOp().Set(Gf.Vec3f(-30, 0, 0))
    l3 = _cyl(f"{path}/Link3/Mesh", 0.055, 0.35)
    UsdGeom.Xformable(l3.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(0, 0.175, 0))
    l3.GetDisplayColorAttr().Set([robot_colour])
    UsdPhysics.CollisionAPI.Apply(l3.GetPrim())

    # Wrist + end effector
    wrist_xf = UsdGeom.Xform.Define(stage, f"{path}/Wrist")
    wrist_xf.AddTranslateOp().Set(Gf.Vec3d(0, 0.35, 0.175))
    ee = _cyl(f"{path}/Wrist/Mesh", 0.04, 0.08)
    UsdGeom.Xformable(ee.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(0, 0.04, 0))
    ee.GetDisplayColorAttr().Set([Gf.Vec3f(0.3, 0.3, 0.3)])

    # Reach envelope marker (visual only — used by veritas spatial audit)
    reach_sphere = UsdGeom.Sphere.Define(stage, f"{path}/ReachEnvelope")
    reach_sphere.GetRadiusAttr().Set(max_reach_m)
    reach_sphere.GetDisplayColorAttr().Set([Gf.Vec3f(0.2, 0.8, 0.2)])
    reach_sphere.GetDisplayOpacityAttr().Set([0.08])
    attr = reach_sphere.GetPrim().CreateAttribute(
        "veritas:reach_radius_m", Sdf.ValueTypeNames.Double
    )
    attr.Set(max_reach_m)
    purpose = UsdGeom.Imageable(reach_sphere.GetPrim())
    purpose.GetPurposeAttr().Set(UsdGeom.Tokens.guide)  # guide purpose = audit only

    return xf.GetPrim(), max_reach_m


# ---------------------------------------------------------------------------
# Conveyor belt
# ---------------------------------------------------------------------------


def add_conveyor(
    stage: Usd.Stage,
    path: str = "/World/Conveyor",
    position: Sequence[float] = (0, 0, 0),
    length: float = 3.0,
    width: float = 0.5,
    height: float = 0.85,
    belt_speed_mps: float = 0.3,
    colour: Sequence[float] = (0.3, 0.3, 0.35),
) -> Usd.Prim:
    """
    Conveyor belt: structural frame + kinematic belt surface.
    belt_speed_mps is stored as metadata for physics scripts.
    """
    xf = _make_xform(stage, path, position)
    _add_semantics(xf, "conveyor")

    # Store belt speed as custom attribute for physics / veritas
    xf.CreateAttribute("conveyor:belt_speed_mps", Sdf.ValueTypeNames.Double).Set(belt_speed_mps)

    hw, hl = width / 2, length / 2
    leg_h = height - 0.05

    # Frame body
    frame_mesh = _box_mesh(stage, f"{path}/Frame/Mesh", (hw, 0.05, hl))
    _make_xform(stage, f"{path}/Frame", (0, height, 0))
    frame_mesh.GetDisplayColorAttr().Set([Gf.Vec3f(*colour)])
    UsdPhysics.CollisionAPI.Apply(frame_mesh.GetPrim())

    # Belt surface (kinematic rigid body — surface velocity applied in sim)
    belt_xf = _make_xform(stage, f"{path}/Belt", (0, height + 0.01, 0))
    belt_mesh = _box_mesh(stage, f"{path}/Belt/Mesh", (hw - 0.01, 0.01, hl - 0.01))
    belt_mesh.GetDisplayColorAttr().Set([Gf.Vec3f(0.15, 0.15, 0.15)])
    UsdPhysics.RigidBodyAPI.Apply(belt_xf)
    rb = UsdPhysics.RigidBodyAPI(belt_xf)
    rb.GetKinematicEnabledAttr().Set(True)
    UsdPhysics.CollisionAPI.Apply(belt_mesh.GetPrim())
    cm = UsdPhysics.MeshCollisionAPI.Apply(belt_mesh.GetPrim())
    cm.GetApproximationAttr().Set("convexHull")
    # Store velocity direction (along +Z axis)
    belt_xf.CreateAttribute("conveyor:velocity_mps", Sdf.ValueTypeNames.Double).Set(belt_speed_mps)
    belt_xf.CreateAttribute("conveyor:velocity_axis", Sdf.ValueTypeNames.String).Set("Z")

    # Legs (4)
    for li, (lx, lz) in enumerate(
        [
            (-hw + 0.05, -hl + 0.1),
            (hw - 0.05, -hl + 0.1),
            (-hw + 0.05, hl - 0.1),
            (hw - 0.05, hl - 0.1),
        ]
    ):
        leg = _box_mesh(stage, f"{path}/Leg_{li}/Mesh", (0.03, leg_h / 2, 0.03))
        _make_xform(stage, f"{path}/Leg_{li}", (lx, leg_h / 2, lz))
        leg.GetDisplayColorAttr().Set([Gf.Vec3f(*colour)])
        UsdPhysics.CollisionAPI.Apply(leg.GetPrim())

    return xf


# ---------------------------------------------------------------------------
# Zone markers (pick / place / clash)
# ---------------------------------------------------------------------------


def add_zone(
    stage: Usd.Stage,
    path: str,
    position: Sequence[float],
    radius: float = 0.15,
    colour: Sequence[float] = (0.0, 1.0, 0.0),
    label: str = "zone",
    zone_type: str = "pick",  # "pick" | "place" | "clash"
) -> Usd.Prim:
    """Sphere marker for pick/place/clash zones. Guide purpose — audit only."""
    xf = _make_xform(stage, path, position)
    sphere = UsdGeom.Sphere.Define(stage, f"{path}/Sphere")
    sphere.GetRadiusAttr().Set(radius)
    sphere.GetDisplayColorAttr().Set([Gf.Vec3f(*colour)])
    sphere.GetDisplayOpacityAttr().Set([0.35])
    UsdGeom.Imageable(sphere.GetPrim()).GetPurposeAttr().Set(UsdGeom.Tokens.guide)

    _add_semantics(xf, label)
    xf.CreateAttribute("veritas:zone_type", Sdf.ValueTypeNames.String).Set(zone_type)
    xf.CreateAttribute("veritas:zone_radius_m", Sdf.ValueTypeNames.Double).Set(radius)
    return xf
