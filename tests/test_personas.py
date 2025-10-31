"""Lightweight tests covering persona registry integrity."""

from __future__ import annotations

from monster_mash_chatroom.models import AuthorKind, ChatMessage
from monster_mash_chatroom.personas import PERSONA_REGISTRY, MonsterPersona


def test_persona_registry_contains_expected_keys() -> None:
    expected = {"witch", "vampire", "ghost", "werewolf", "zombie"}
    assert expected == set(PERSONA_REGISTRY)


def test_persona_prompts_are_non_empty() -> None:
    for persona in PERSONA_REGISTRY.values():
        assert persona.system_prompt.strip()
        assert persona.summary.strip()


def test_persona_emojis_present() -> None:
    for persona in PERSONA_REGISTRY.values():
        assert persona.emoji, f"Persona {persona.key} must define an emoji"


def test_persona_skips_own_messages() -> None:
    ghost = PERSONA_REGISTRY["ghost"]
    monster_message = ChatMessage(
        author="Eloise the Ghost",
        role=AuthorKind.MONSTER,
        content="Boo!",
        persona="ghost",
    )
    backlog = (monster_message,)
    assert ghost.should_respond(monster_message, backlog) is False


def test_persona_respects_monster_streak_cap() -> None:
    persona = MonsterPersona(
        key="tester",
        display_name="Tester",
        summary="",
        system_prompt="",
        respond_probability=1.0,
        max_monster_streak=2,
    )
    backlog = (
        ChatMessage(
            author="A",
            role=AuthorKind.MONSTER,
            content="growl",
            persona="wolf",
        ),
        ChatMessage(
            author="B",
            role=AuthorKind.MONSTER,
            content="snarl",
            persona="ghost",
        ),
    )
    incoming = ChatMessage(
        author="C",
        role=AuthorKind.MONSTER,
        content="hiss",
        persona="vampire",
    )
    backlog_with_incoming = backlog + (incoming,)
    assert persona.should_respond(incoming, backlog_with_incoming) is False


def test_persona_reading_delay_positive() -> None:
    persona = PERSONA_REGISTRY["witch"]
    backlog = (
        ChatMessage(
            author="Human",
            role=AuthorKind.HUMAN,
            content="Hello there!",
            persona=None,
        ),
    )
    message = backlog[-1]
    delay = persona.reading_delay_seconds(message, backlog)
    assert delay > 0
