# veritas

USD scene ground-truth validation: **audit → render → render-validate → segment → vision → verdict**.

Veritas answers the question: *does what the USD stage claims match what actually renders and simulates?*

Designed for factory simulation pipelines running on NVIDIA Isaac Sim, Isaac Lab, and Mission Control.

---

## Install

```bash
pip install -e ".[dev]"
# or just the runtime deps:
pip install pydantic>=2 anthropic>=0.25
```

For full render support, run inside an Isaac Sim Python environment:

```bash
/path/to/isaac-sim/python.sh -m veritas run scene/factory.usd
```

---

## Quickstart

```bash
# USD audit only (no Isaac Sim required — just pxr / usd-core):
veritas audit scene/factory.usda

# Full pipeline (must run inside Isaac Sim Python; needs ANTHROPIC_API_KEY for vision):
export ANTHROPIC_API_KEY=sk-ant-...
veritas run scene/factory.usda --output-dir ./veritas_out

# Skip optional steps:
veritas run scene/factory.usda --no-vision --no-segmentation
```

Both commands print a JSON report to stdout and exit 0 on PASS, 1 on FAIL/WARN.

---

## Architecture

```
veritas/
│
├── interface/              ABCs only — no concrete imports
│   ├── usd_auditor.py      UsdAuditor.audit(stage_path) -> UsdAuditResult
│   ├── renderer.py         Renderer.render(stage_path, output_path) -> RenderResult
│   ├── vision_backend.py   VisionBackend.describe(image_path, context) -> VisionResult
│   ├── segmentor.py        Segmentor.segment(image_path, labels) -> SegmentResult
│   └── sim_validator.py    SimValidator.validate(stage_path) -> dict
│
├── impl/                   Concrete implementations, grouped by domain
│   ├── usd/
│   │   └── prim_auditor.py         pxr.Usd — walks prims, checks SimReady schemas
│   ├── vision/
│   │   └── claude_vision.py        Anthropic Claude (claude-opus-4-6)
│   ├── segmentation/
│   │   └── sam_segmentor.py        Meta SAM (stub — needs checkpoint)
│   └── isaac/
│       ├── isaac_renderer.py       Isaac Sim viewport capture (stub)
│       ├── isaac_sim_validator.py  Isaac Sim physics validator (stub)
│       └── mission_control_validator.py  Fleet validator via REST API (stub)
│
├── core/
│   ├── models.py           Pydantic data models + Verdict enum
│   └── pipeline.py         VeritasPipeline — orchestrates the 6-step loop
│
├── cli/
│   └── main.py             argparse CLI: `veritas audit` and `veritas run`
│
└── __main__.py             python -m veritas entrypoint
```

---

## The 6-step validation loop

```
  ┌─────────────┐
  │  Edit USD   │
  └──────┬──────┘
         │  1. USD Audit
         ▼
  ┌─────────────────────────────────────────────────┐
  │  PrimAuditor: walk all prims, check schemas,    │
  │  verify UsdPhysics on robots, semantics labels  │
  └──────┬──────────────────────────────────────────┘
         │  2. Render
         ▼
  ┌─────────────────────────────────────────────────┐
  │  IsaacSimRenderer: load stage, step N frames,   │
  │  capture viewport screenshot → PNG              │
  └──────┬──────────────────────────────────────────┘
         │  3. Render Validate
         ▼
  ┌─────────────────────────────────────────────────┐
  │  Size > 10 KB  AND  entropy > 0.5               │
  │  Reject black / blank frames early              │
  └──────┬──────────────────────────────────────────┘
         │  4. Segment  (optional)
         ▼
  ┌─────────────────────────────────────────────────┐
  │  SamSegmentor: instance masks, labels           │
  └──────┬──────────────────────────────────────────┘
         │  5. Vision cross-check  (optional)
         ▼
  ┌─────────────────────────────────────────────────┐
  │  ClaudeVisionBackend: describe scene,           │
  │  extract entity list                            │
  └──────┬──────────────────────────────────────────┘
         │  6. Verdict
         ▼
  ┌─────────────────────────────────────────────────┐
  │  VeritasReport: PASS / WARN / FAIL + reason     │
  └─────────────────────────────────────────────────┘
```

---

## Configuration

| Env var | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Required for `ClaudeVisionBackend` |

---

## Running tests

```bash
pip install pytest pydantic
pytest tests/ -v
```

Tests in `tests/test_pipeline.py` use mock auditors and renderers — no Isaac Sim or API keys needed.
