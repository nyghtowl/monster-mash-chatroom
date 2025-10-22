"""Runtime configuration for the Monster Mash Chatroom demo."""
from __future__ import annotations

import json
import os
from enum import Enum
from functools import lru_cache
from typing import Annotated

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings


class BusBackend(str, Enum):
    IN_MEMORY = "in-memory"
    KAFKA = "kafka"


class KafkaBusSettings(BaseModel):
    brokers: Annotated[
        list[str],
        Field(default_factory=list),
    ]
    topic: str = "monster.chat"

    @field_validator("brokers", mode="before")
    @classmethod
    def split_brokers(
        cls, value: list[str] | dict[str, str] | str | None
    ) -> list[str]:
        raw_candidates: list[str]
        if isinstance(value, str):
            raw_candidates = value.split(",")
        elif isinstance(value, dict):
            ordered = sorted(
                value.items(),
                key=lambda kv: int(kv[0]) if kv[0].isdigit() else kv[0],
            )
            raw_candidates = [item[1] for item in ordered]
        elif value is None:
            fallback = os.getenv("KAFKA_BROKERS") or ""
            raw_candidates = fallback.split(",") if fallback else []
        else:
            raw_candidates = list(value)

        cleaned: list[str] = []
        for broker in raw_candidates:
            if not isinstance(broker, str):
                continue
            trimmed = broker.strip()
            if trimmed:
                cleaned.append(trimmed)
        return cleaned

    @field_validator("topic", mode="before")
    @classmethod
    def default_topic(cls, value: str | None) -> str:
        if value and value.strip():
            return value
        fallback = os.getenv("KAFKA_TOPIC")
        if fallback and fallback.strip():
            return fallback.strip()
        return "monster.chat"


class MessageBusSettings(BaseModel):
    backend: BusBackend = BusBackend.IN_MEMORY
    history_limit: int = 200
    namespace: str = "monster-mash-chatroom"
    kafka: KafkaBusSettings = Field(default_factory=KafkaBusSettings)

    @field_validator("namespace", mode="before")
    @classmethod
    def default_namespace(cls, value: str | None) -> str | None:
        if value and value.strip():
            return value
        fallback = os.getenv("SERVICE_NAMESPACE")
        if fallback and fallback.strip():
            return fallback.strip()
        return value

    @field_validator("history_limit", mode="before")
    @classmethod
    def coerce_history_limit(cls, value: int | str | None) -> int | str | None:
        if isinstance(value, str) and value.strip():
            return value
        if value not in (None, "", " "):
            return value
        fallback = os.getenv("MONSTER_HISTORY_LIMIT")
        if fallback and fallback.strip():
            return fallback.strip()
        return value


class ModelRouting(BaseModel):
    default_model: str = "gpt-4o-mini"
    persona_model_map: Annotated[dict[str, str], Field(default_factory=dict)]

    @field_validator("persona_model_map", mode="before")
    @classmethod
    def parse_json_map(cls, value: dict[str, str] | str) -> dict[str, str]:
        if isinstance(value, str) and value.strip():
            return json.loads(value)
        return value

    def for_persona(self, persona_key: str) -> str:
        mapping = dict(self.persona_model_map)
        return mapping.get(persona_key, self.default_model)


class Settings(BaseSettings):
    bus: MessageBusSettings = MessageBusSettings()
    demo_mode: bool = True
    model_routing: ModelRouting = ModelRouting()

    class Config:
        env_prefix = ""
        env_nested_delimiter = "__"
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Allow extra env vars for LiteLLM


@lru_cache
def get_settings() -> Settings:
    """Return memoized settings instance."""

    return Settings()  # type: ignore[arg-type]
