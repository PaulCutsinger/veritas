"""
scene/render_demos.py — Render all 5 veritas demo scenes via Isaac Sim.

Boots SimulationApp once (expensive), then renders each scene in sequence.
Writes PNGs to demos/ and JSON veritas reports to demos/reports/.

Usage (must be run from repo root):
    python3 scene/render_demos.py
    python3 scene/render_demos.py --scene demo1_shelf_boxes  # single scene
    python3 scene/render_demos.py --width 1920 --height 1080 --warmup 120
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Boot Isaac Sim FIRST — before any other omni/pxr imports
print("Booting Isaac Sim (headless RTX)...", flush=True)
from isaacsim import SimulationApp  # noqa: E402

app = SimulationApp({"headless": True, "renderer": "RayTracedLighting"})
print("Isaac Sim ready.", flush=True)

# Now safe to import omni / veritas

from veritas.core.models import Verdict  # noqa: E402
from veritas.impl.isaac.isaac_renderer import IsaacSimRenderer  # noqa: E402
from veritas.impl.usd.prim_auditor import PrimAuditor  # noqa: E402
from veritas.impl.usd.spatial_auditor import run_spatial_audits  # noqa: E402

# ---------------------------------------------------------------------------
# Scene catalogue
# ---------------------------------------------------------------------------

SCENES = [
    {
        "name": "demo1_shelf_boxes",
        "file": "scene/usd/demo1_shelf_boxes.usda",
        "title": "Demo 1 — Shelf with Boxes",
        "caption": "Industrial shelf unit with 12 boxes. USD compliance + SimReady audit.",
        "camera": "shelf",
    },
    {
        "name": "demo2_robot_table",
        "file": "scene/usd/demo2_robot_table.usda",
        "title": "Demo 2 — Robot on Table",
        "caption": "FANUC CRX-10iA/L simplified arm on work table. ArticulationRootAPI validated.",
        "camera": "iso",
    },
    {
        "name": "demo3_conveyor_physics",
        "file": "scene/usd/demo3_conveyor_physics.usda",
        "title": "Demo 3 — Conveyor with Physics Boxes",
        "caption": "Kinematic belt + rigid-body boxes. Belt speed 0.3 m/s stored as metadata.",
        "camera": "conveyor",
    },
    {
        "name": "demo4_robot_pick_place",
        "file": "scene/usd/demo4_robot_pick_place.usda",
        "title": "Demo 4 — Robot Pick / Place Zones",
        "caption": "Pick zone (green) and place zone (red) both within CRX-10iA/L 1.249 m reach.",
        "camera": "iso",
    },
    {
        "name": "demo5_robot_conveyor_clash",
        "file": "scene/usd/demo5_robot_conveyor_clash.usda",
        "title": "Demo 5 — Robot + Conveyor CLASH ALERT",
        "caption": "Robot reach envelope overlaps conveyor by 0.399 m — CRITICAL clash detected.",
        "camera": "clash",
    },
]


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def render_scene(
    scene_meta: dict,
    out_dir: Path,
    report_dir: Path,
    width: int,
    height: int,
    warmup: int,
) -> dict:
    name = scene_meta["name"]
    stage_path = str(REPO_ROOT / scene_meta["file"])
    output_png = str(out_dir / f"{name}.png")
    report_path = report_dir / f"{name}_report.json"

    print(f"\n{'=' * 60}", flush=True)
    print(f"  {scene_meta['title']}", flush=True)
    print(f"{'=' * 60}", flush=True)
    print(f"  Stage: {stage_path}", flush=True)

    # 1. USD audit (pxr — no SimulationApp needed for this step)
    print("  [1/3] USD audit...", flush=True)
    auditor = PrimAuditor(run_compliance=True, check_semantics=False)
    audit = auditor.audit(stage_path)
    print(f"  → {audit.prim_count} prims, {len(audit.schema_violations)} violations", flush=True)

    # 2. Spatial audit (reach + clash)
    print("  [2/3] Spatial audit...", flush=True)
    spatial = run_spatial_audits(stage_path)
    spatial_violations = spatial.get("all_violations", [])
    print(f"  → {len(spatial_violations)} spatial violations", flush=True)
    for v in spatial_violations:
        print(f"      {v}", flush=True)

    # 3. Render
    print("  [3/3] Rendering...", flush=True)
    renderer = IsaacSimRenderer(
        warmup_frames=warmup, width=width, height=height, camera_preset=scene_meta["camera"]
    )
    t0 = time.time()
    render = renderer.render(stage_path, output_png)
    elapsed = time.time() - t0
    kb = render.file_size_bytes // 1024
    print(f"  → {output_png} ({kb} KB, entropy={render.entropy:.2f}) in {elapsed:.1f}s", flush=True)
    print(f"  → valid={render.valid}", flush=True)

    # Verdict
    all_violations = audit.schema_violations + spatial_violations
    if not render.valid:
        verdict = Verdict.FAIL
        reason = (
            f"Invalid render (size={render.file_size_bytes} bytes, entropy={render.entropy:.3f})"
        )
    elif any("[clash:critical]" in v for v in all_violations):
        verdict = Verdict.FAIL
        reason = (
            f"CRITICAL clash detected: {next(v for v in all_violations if '[clash:critical]' in v)}"
        )
    elif all_violations:
        verdict = Verdict.WARN
        reason = f"{len(all_violations)} violations: " + "; ".join(all_violations[:2])
    else:
        verdict = Verdict.PASS
        reason = f"All checks passed. {audit.prim_count} prims, render valid."

    print(f"  VERDICT: {verdict.value} — {reason[:100]}", flush=True)

    # Report
    report = {
        "name": name,
        "title": scene_meta["title"],
        "caption": scene_meta["caption"],
        "stage_path": stage_path,
        "render": {
            "path": output_png,
            "file_size_bytes": render.file_size_bytes,
            "entropy": render.entropy,
            "valid": render.valid,
            "elapsed_s": round(elapsed, 2),
        },
        "usd_audit": {
            "prim_count": audit.prim_count,
            "violations": audit.schema_violations,
        },
        "spatial": spatial,
        "verdict": verdict.value,
        "reason": reason,
    }
    report_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"  Report: {report_path}", flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", help="Render one scene by name (e.g. demo1_shelf_boxes)")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--warmup", type=int, default=80)
    args = parser.parse_args()

    out_dir = REPO_ROOT / "demos"
    report_dir = REPO_ROOT / "demos" / "reports"
    out_dir.mkdir(exist_ok=True)
    report_dir.mkdir(exist_ok=True)

    scenes = [s for s in SCENES if not args.scene or s["name"] == args.scene]
    if not scenes:
        print(f"ERROR: no scene named '{args.scene}'", flush=True)
        sys.exit(1)

    results = []
    for scene_meta in scenes:
        try:
            r = render_scene(scene_meta, out_dir, report_dir, args.width, args.height, args.warmup)
            results.append(r)
        except Exception as e:
            print(f"  ERROR rendering {scene_meta['name']}: {e}", flush=True)
            import traceback

            traceback.print_exc()

    print(f"\n{'=' * 60}", flush=True)
    print(f"  SUMMARY: {len(results)}/{len(scenes)} scenes rendered", flush=True)
    for r in results:
        print(f"  [{r['verdict']:4s}] {r['name']}", flush=True)
    print(f"{'=' * 60}", flush=True)

    app.close()


if __name__ == "__main__":
    main()
