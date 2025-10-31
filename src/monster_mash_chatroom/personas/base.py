"""Persona definitions and behavior helpers."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from monster_mash_chatroom.models import AuthorKind, ChatMessage


@dataclass(slots=True)
class MonsterPersona:
    key: str
    display_name: str
    summary: str
    system_prompt: str
    emoji: str = ""
    trigger_keywords: Sequence[str] = field(default_factory=tuple)
    respond_probability: float = 0.2
    max_monster_streak: int = 6
    reading_delay_range: tuple[float, float] = (0.6, 1.4)
    typing_delay_range: tuple[float, float] = (0.8, 1.6)

    def should_respond(
        self, message: ChatMessage, backlog: Sequence[ChatMessage]
    ) -> bool:
        """Decide whether this persona should respond based on triggers, probability, and conversation flow."""
        if message.persona == self.key:
            return False

        lowered = message.content.lower()
        keyword_hit = any(keyword in lowered for keyword in self.trigger_keywords)

        if message.role == AuthorKind.HUMAN:
            if keyword_hit:
                return True
            return random.random() < self.respond_probability

        monster_streak = 0
        for entry in reversed(backlog):
            if entry.role == AuthorKind.HUMAN:
                break
            monster_streak += 1

        if monster_streak > self.max_monster_streak:
            return False

        monster_probability = max(self.respond_probability * 0.4, 0.05)
        if keyword_hit:
            monster_probability = max(monster_probability, 0.25)

        return random.random() < monster_probability

    def format_demo_reply(self, message: ChatMessage) -> str:
        """Generate a canned demo reply for this persona."""
        template = (
            "{name} senses spectral winds in '{snippet}'"
            " and replies with eerie flair."
        )
        snippet = message.content.strip().split("\n")[0][:60]
        return template.format(name=self.display_name, snippet=snippet)

    def reading_delay_seconds(
        self, message: ChatMessage, backlog: Sequence[ChatMessage]
    ) -> float:
        """Calculate reading delay based on message length and conversation context."""
        base = random.uniform(*self.reading_delay_range)
        length_bonus = min(len(message.content) / 160, 2.0)
        streak_bonus = 0.0
        if backlog and backlog[-1] is message:
            streak_bonus = min(len(backlog), 3) * 0.1
        return base + length_bonus + streak_bonus

    def typing_delay_seconds(self, reply: str) -> float:
        """Calculate typing delay based on reply length."""
        base = random.uniform(*self.typing_delay_range)
        length_bonus = min(len(reply) / 120, 3.0)
        return base + length_bonus
