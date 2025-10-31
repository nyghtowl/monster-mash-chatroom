"""Shared Pydantic models for chat events."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class AuthorKind(str, Enum):
    HUMAN = "human"
    MONSTER = "monster"


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    author: str
    role: AuthorKind
    content: str
    persona: str | None = None
    persona_emoji: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SendMessageRequest(BaseModel):
    author: str | None = Field(default="Human Visitor")
    content: str
    role: Literal[AuthorKind.HUMAN, AuthorKind.MONSTER] = AuthorKind.HUMAN
    persona: str | None = None

    def to_chat_message(self) -> ChatMessage:
        """Convert the request to a ChatMessage with metadata."""
        return ChatMessage(
            author=self.author or "Anonymous",
            role=self.role,
            content=self.content,
            persona=self.persona,
            persona_emoji=None,
        )
