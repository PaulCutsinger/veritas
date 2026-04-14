"""
veritas.interface.sim_validator
--------------------------------
ABC for simulation validators (Isaac Sim, Mission Control, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class SimValidator(ABC):
    @abstractmethod
    def validate(self, stage_path: str) -> dict:
        """
        Validate the simulation state for the given stage.

        Returns a dict with keys:
            loaded (bool)         — stage loaded without errors
            simulated (bool)      — at least one physics step completed
            robots_active (int)   — number of active robot prims found
            errors (list[str])    — any error messages encountered
        """
        ...
