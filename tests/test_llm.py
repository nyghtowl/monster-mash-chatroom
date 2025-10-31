"""Tests for LLM response helpers."""

from __future__ import annotations

import pytest

from monster_mash_chatroom.config import Settings
from monster_mash_chatroom.llm import generate_persona_reply
from monster_mash_chatroom.models import AuthorKind, ChatMessage
from monster_mash_chatroom.personas import PERSONA_REGISTRY


@pytest.mark.asyncio
async def test_generate_persona_reply_demo_mode() -> None:
    persona = PERSONA_REGISTRY["witch"]
    history = [
        ChatMessage(
            author="Tester",
            role=AuthorKind.HUMAN,
            content="How's the brew tonight?",
        )
    ]
    settings = Settings(demo_mode=True)
    reply = await generate_persona_reply(persona, history, settings)
    assert reply
    assert persona.display_name.split()[0] in reply


@pytest.mark.asyncio
async def test_demo_response_fallback(monkeypatch):
    """When LiteLLM is unavailable, demo responses are used."""
    monkeypatch.setattr("monster_mash_chatroom.llm.litellm", None)
    persona = PERSONA_REGISTRY["witch"]
    history = [
        ChatMessage(
            author="Tester",
            role=AuthorKind.HUMAN,
            content="Is the cauldron simmering tonight?",
        )
    ]
    settings = Settings(demo_mode=False)
    reply = await generate_persona_reply(persona, history, settings)
    assert reply
    assert persona.display_name.split()[0] in reply
