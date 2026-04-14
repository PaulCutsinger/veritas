"""
tests/test_prim_auditor.py
---------------------------
Integration tests for PrimAuditor using real USD stages (via usd-core).
Skipped automatically if usd-core / pxr is not installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pxr", reason="usd-core not installed")

from veritas.core.models import UsdAuditResult
from veritas.impl.usd.prim_auditor import PrimAuditor

FIXTURES = Path(__file__).parent / "fixtures"
MINIMAL_USD = FIXTURES / "minimal.usda"


class TestPrimAuditorBasic:
    def test_opens_stage_returns_result(self):
        auditor = PrimAuditor(run_compliance=False, check_semantics=False)
        result = auditor.audit(str(MINIMAL_USD))
        assert isinstance(result, UsdAuditResult)
        assert result.stage_path == str(MINIMAL_USD)

    def test_counts_prims(self):
        auditor = PrimAuditor(run_compliance=False, check_semantics=False)
        result = auditor.audit(str(MINIMAL_USD))
        # /World, /World/ConveyorBelt, /World/Robot_0
        assert result.prim_count == 3

    def test_detects_robot_prim(self):
        """Robot_0 has no physics schema → violation."""
        auditor = PrimAuditor(run_compliance=False, check_semantics=False)
        result = auditor.audit(str(MINIMAL_USD))
        robot_violations = [v for v in result.schema_violations if "Robot_0" in v]
        assert len(robot_violations) == 1
        assert "simready:physics" in robot_violations[0]

    def test_semantics_check_warns_all_xforms(self):
        auditor = PrimAuditor(run_compliance=False, check_semantics=True)
        result = auditor.audit(str(MINIMAL_USD))
        sem_violations = [v for v in result.schema_violations if "simready:semantics" in v]
        # World, ConveyorBelt, Robot_0 — all Xform, none have semantics labels
        assert len(sem_violations) == 3

    def test_prim_paths_populated(self):
        auditor = PrimAuditor(run_compliance=False, check_semantics=False)
        result = auditor.audit(str(MINIMAL_USD))
        paths = [p.path for p in result.prims]
        assert "/World" in paths
        assert "/World/Robot_0" in paths
        assert "/World/ConveyorBelt" in paths


class TestPrimAuditorComplianceChecker:
    def test_compliance_runs_without_crash(self):
        """ComplianceChecker should complete on a valid stage (may produce warnings)."""
        auditor = PrimAuditor(run_compliance=True, check_semantics=False)
        result = auditor.audit(str(MINIMAL_USD))
        # All compliance results are strings
        for v in result.schema_violations:
            assert isinstance(v, str)

    def test_compliance_tags_prefixed(self):
        """Compliance violations must use [compliance:*] prefix for traceability."""
        auditor = PrimAuditor(run_compliance=True, check_semantics=False)
        result = auditor.audit(str(MINIMAL_USD))
        compliance_violations = [v for v in result.schema_violations if v.startswith("[compliance")]
        # Tags are correctly formatted (may be 0 if stage is clean)
        valid_prefixes = ("[compliance:error]", "[compliance:warn]", "[compliance:fail]")
        for v in compliance_violations:
            assert v.startswith(valid_prefixes)

    def test_disabled_compliance_no_compliance_tags(self):
        """When run_compliance=False, no [compliance:*] entries should appear."""
        auditor = PrimAuditor(run_compliance=False, check_semantics=False)
        result = auditor.audit(str(MINIMAL_USD))
        compliance_violations = [v for v in result.schema_violations if "[compliance" in v]
        assert compliance_violations == []


class TestPrimAuditorErrorHandling:
    def test_raises_on_missing_file(self):
        auditor = PrimAuditor()
        with pytest.raises(RuntimeError, match="Failed to open"):
            auditor.audit("/nonexistent/path/stage.usd")

    def test_transform_is_16_floats(self):
        auditor = PrimAuditor(run_compliance=False, check_semantics=False)
        result = auditor.audit(str(MINIMAL_USD))
        for prim in result.prims:
            assert len(prim.transform) == 16
            assert all(isinstance(v, float) for v in prim.transform)
