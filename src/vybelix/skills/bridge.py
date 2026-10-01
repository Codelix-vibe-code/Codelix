"""Stable, fail-closed boundary between Vybelix agents and local skills."""
from __future__ import annotations

from typing import Any

from .manager import SkillManager


class SkillBridge:
    """Supplies explicitly selected skill instructions as untrusted data.

    This interface never executes a skill. Execution remains blocked until an
    operating-system sandbox backend is available and verified.
    """

    def __init__(self, manager: SkillManager):
        self.manager = manager

    def context_for(self, role: str, skill_ids: list[str] | None = None) -> list[dict[str, Any]]:
        return self.manager.agent_context(role, skill_ids)
