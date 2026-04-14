"""
veritas.interface.renderer
---------------------------
ABC for scene renderers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.models import RenderResult


class Renderer(ABC):
    @abstractmethod
    def render(self, stage_path: str, output_path: str) -> RenderResult: ...
