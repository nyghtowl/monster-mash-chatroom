"""Registry of all monster personas."""

from __future__ import annotations

from .base import MonsterPersona
from .ghost import GHOST
from .vampire import VAMPIRE
from .werewolf import WEREWOLF
from .witch import WITCH
from .zombie import ZOMBIE

PERSONA_REGISTRY: dict[str, MonsterPersona] = {
    persona.key: persona for persona in [WITCH, VAMPIRE, GHOST, WEREWOLF, ZOMBIE]
}

__all__ = ["PERSONA_REGISTRY", "MonsterPersona"]
