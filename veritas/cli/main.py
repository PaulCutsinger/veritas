"""
veritas.cli.main
-----------------
Command-line interface for the Veritas USD validation tool.

Usage:
    veritas audit <stage.usd>         — USD audit only, prints JSON
    veritas run   <stage.usd>         — full pipeline, prints report
    veritas run   <stage.usd> --no-vision --no-segmentation
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="veritas",
        description="USD scene ground-truth validation: audit, render, segment, vision cross-check.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ------------------------------------------------------------------
    # veritas audit <stage.usd>
    # ------------------------------------------------------------------
    audit_p = sub.add_parser(
        "audit",
        help="Run USD audit only and print the result as JSON.",
    )
    audit_p.add_argument("stage", help="Path to the .usd / .usda stage to audit.")
    audit_p.add_argument(
        "--output-dir",
        default="./veritas_out",
        help="Directory for output files (default: ./veritas_out).",
    )

    # ------------------------------------------------------------------
    # veritas run <stage.usd>
    # ------------------------------------------------------------------
    run_p = sub.add_parser(
        "run",
        help="Run the full validation pipeline and print the VeritasReport.",
    )
    run_p.add_argument("stage", help="Path to the .usd / .usda stage to validate.")
    run_p.add_argument(
        "--output-dir",
        default="./veritas_out",
        help="Directory for output files (default: ./veritas_out).",
    )
    run_p.add_argument(
        "--no-vision",
        action="store_true",
        help="Skip the Claude vision cross-check step.",
    )
    run_p.add_argument(
        "--no-segmentation",
        action="store_true",
        help="Skip the SAM segmentation step.",
    )

    return parser


def _cmd_audit(args: argparse.Namespace) -> int:
    """Run USD audit only and print JSON to stdout."""
    from ..impl.usd.prim_auditor import PrimAuditor

    auditor = PrimAuditor()
    try:
        result = auditor.audit(args.stage)
    except (ImportError, RuntimeError) as exc:
        _err(f"Audit failed: {exc}")
        return 1

    print(result.model_dump_json(indent=2))
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """Run the full validation pipeline."""
    from ..impl.usd.prim_auditor import PrimAuditor
    from ..impl.isaac.isaac_renderer import IsaacSimRenderer
    from ..core.pipeline import VeritasPipeline

    auditor = PrimAuditor()

    # Renderer — stubs NotImplementedError if not inside Isaac Sim.
    renderer = IsaacSimRenderer()

    vision = None
    if not args.no_vision:
        import os
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                from ..impl.vision.claude_vision import ClaudeVisionBackend
                vision = ClaudeVisionBackend()
            except Exception as exc:
                _warn(f"Vision backend unavailable, skipping: {exc}")
        else:
            _warn("ANTHROPIC_API_KEY not set — skipping vision check. "
                  "Pass --no-vision to suppress this warning.")

    segmentor = None
    if not args.no_segmentation:
        try:
            from ..impl.segmentation.sam_segmentor import SamSegmentor  # noqa: F401
            # Segmentor not yet configured — skip silently.
            _warn("SAM segmentor not configured (no checkpoint provided) — skipping.")
        except ImportError:
            _warn("segment-anything not installed — skipping segmentation.")

    pipeline = VeritasPipeline(
        auditor=auditor,
        renderer=renderer,
        vision=vision,
        segmentor=segmentor,
        output_dir=args.output_dir,
    )

    try:
        report = pipeline.run(args.stage)
    except NotImplementedError as exc:
        _err(
            f"Pipeline step not available in this environment: {exc}\n"
            "Hint: run `veritas run` inside an Isaac Sim Python session for "
            "full render+sim support, or use `veritas audit` for USD-only checks."
        )
        return 1
    except Exception as exc:
        _err(f"Pipeline failed: {exc}")
        return 1

    print(report.model_dump_json(indent=2))
    verdict = report.verdict
    print(f"\nVerdict: {verdict.value} — {report.reason}", file=sys.stderr)
    return 0 if verdict.value == "PASS" else 1


def _err(msg: str) -> None:
    print(f"[veritas] ERROR: {msg}", file=sys.stderr)


def _warn(msg: str) -> None:
    print(f"[veritas] WARN:  {msg}", file=sys.stderr)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "audit":
        sys.exit(_cmd_audit(args))
    elif args.command == "run":
        sys.exit(_cmd_run(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
