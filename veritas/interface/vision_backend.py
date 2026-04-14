"""
veritas.interface.vision_backend
---------------------------------
ABC for vision/LLM backends that describe rendered images.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.models import VisionResult


class VisionBackend(ABC):
    @abstractmethod
    def describe(self, image_path: str, context: str = "") -> VisionResult: ...
