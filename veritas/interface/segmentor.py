"""
veritas.interface.segmentor
----------------------------
ABC for image segmentation backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.models import SegmentResult


class Segmentor(ABC):
    @abstractmethod
    def segment(self, image_path: str, labels: list[str] | None = None) -> SegmentResult: ...
