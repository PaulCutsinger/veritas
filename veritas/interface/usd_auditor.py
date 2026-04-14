"""
veritas.interface.usd_auditor
------------------------------
ABC for USD stage auditors.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.models import UsdAuditResult


class UsdAuditor(ABC):
    @abstractmethod
    def audit(self, stage_path: str) -> UsdAuditResult: ...
