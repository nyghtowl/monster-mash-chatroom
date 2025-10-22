"""Utilities for calling LLMs or generating demo responses."""
from __future__ import annotations

import logging
import random
from collections.abc import Iterable

from .config import ModelRouting, Settings, get_settings
from .models import AuthorKind, ChatMessage
from .personas import MonsterPersona

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency import
    import litellm  # type: ignore[import-untyped]
    from litellm import (  # type: ignore[attr-defined]
        exceptions as litellm_exceptions,
    )
except ImportError:  # pragma: no cover - optional dependency missing
    litellm = None  # type: ignore[assignment]

    class LiteLLMException(Exception):  # type: ignore[override]
        """Placeholder raised when LiteLLM is unavailable."""
else:  # pragma: no cover - executed when LiteLLM is available
    LiteLLMException = getattr(  # type: ignore[assignment]
        litellm_exceptions,
        "LiteLLMException",
        Exception,
    )


async def generate_persona_reply(
    persona: MonsterPersona,
    history: Iterable[ChatMessage],
    settings: Settings | None = None,
) -> str:
    if settings is None:
        settings = get_settings()
    history_list: list[ChatMessage] = list(history)
    if settings.demo_mode or litellm is None:
        logger.info(
            "🎭 DEMO MODE: persona=%s (demo_mode=%s, litellm_available=%s)",
            persona.key,
            settings.demo_mode,
            litellm is not None,
        )
        return _demo_reply(persona, history_list)
    try:
        reply = await _llm_reply(persona, history_list, settings)
        logger.info("🤖 LLM RESPONSE: persona=%s", persona.key)
        return reply
    except LiteLLMException as exc:
        model = settings.model_routing.for_persona(persona.key)
        fallback_model = settings.model_routing.default_model

        # Try fallback to default model if the persona-specific model failed
        if model != fallback_model:
            logger.warning(
                "LLM call failed for persona=%s model=%s: %s. "
                "Trying fallback to default model=%s",
                persona.key,
                model,
                exc,
                fallback_model,
            )
            try:
                # Create temporary settings with fallback model
                fallback_settings = Settings(
                    demo_mode=False,
                    bus=settings.bus,
                    model_routing=ModelRouting(
                        default_model=fallback_model,
                        persona_model_map={},
                    ),
                )
                reply = await _llm_reply(
                    persona, history_list, fallback_settings
                )
                logger.info(
                    "✅ Fallback LLM success: persona=%s model=%s",
                    persona.key,
                    fallback_model,
                )
                return reply
            except LiteLLMException as fallback_exc:
                logger.warning(
                    "Fallback LLM also failed for persona=%s model=%s: %s. "
                    "Using demo response.",
                    persona.key,
                    fallback_model,
                    fallback_exc,
                )
        else:
            logger.warning(
                "LLM call failed for persona=%s model=%s: %s. "
                "No fallback available (already using default). "
                "Using demo response.",
                persona.key,
                model,
                exc,
            )

        return _demo_reply(persona, history_list)


def _demo_reply(
    persona: MonsterPersona, history: Iterable[ChatMessage]
) -> str:
    as_list = list(history)
    latest = as_list[-1] if as_list else None
    if latest is None:
        placeholder = ChatMessage(
            author="Narrator",
            role="human",
            content="...",
        )
        reply = persona.format_demo_reply(placeholder)
        logger.debug(
            "Generated placeholder demo reply for persona=%s",
            persona.key,
        )
        return reply
    seed = hash(latest.id) % 999999
    random.seed(seed)

    # More natural fallback responses without "hums"
    templates = [
        f"{persona.display_name}: Interesting... *{persona.emoji}*",
        f"{persona.display_name}: Tell me more about that.",
        f"{persona.display_name}: *nods* I see.",
        f"{persona.display_name}: Hmm, fascinating perspective.",
        f"{persona.display_name}: *listens intently*",
        f"{persona.display_name}: That reminds me of something...",
    ]
    return random.choice(templates)


async def _llm_reply(
    persona: MonsterPersona,
    history: Iterable[ChatMessage],
    settings: Settings,
) -> str:
    if litellm is None:  # pragma: no cover - defensive guard
        raise LiteLLMException("LiteLLM is not available")
    model_name = settings.model_routing.for_persona(persona.key)
    logger.info(
        "🔮 Calling LLM: persona=%s model=%s",
        persona.key,
        model_name,
    )
    messages = [
        {
            "role": "system",
            "content": persona.system_prompt,
        }
    ]
    for message in history:
        role = "assistant" if message.role == AuthorKind.MONSTER else "user"
        content = message.content
        if message.persona and message.persona != persona.key:
            content = f"[{message.persona}] {content}"
        messages.append({"role": role, "content": content})
    completion = await litellm.acompletion(model=model_name, messages=messages)
    return completion["choices"][0]["message"]["content"].strip()
