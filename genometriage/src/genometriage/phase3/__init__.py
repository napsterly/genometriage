"""Deterministic Phase 3 conflict arbitration."""

from .arbitration import arbitrate_candidate
from .runner import ConflictArbitrationSystem

__all__ = ["ConflictArbitrationSystem", "arbitrate_candidate"]
