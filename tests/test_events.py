import pytest

from monster_mash_chatroom.config import (
    BusBackend,
    KafkaBusSettings,
    MessageBusSettings,
)
from monster_mash_chatroom.events import InMemoryEventBus, build_event_bus


def test_kafka_bus_settings_default_to_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KAFKA_BROKERS", raising=False)
    settings = KafkaBusSettings()
    assert settings.brokers == []


@pytest.mark.anyio
async def test_build_event_bus_in_memory_backend() -> None:
    settings = MessageBusSettings(backend=BusBackend.IN_MEMORY)
    bus = await build_event_bus(settings)
    assert isinstance(bus, InMemoryEventBus)
    await bus.stop()


@pytest.mark.anyio
async def test_build_event_bus_kafka_without_brokers_falls_back() -> None:
    settings = MessageBusSettings(
        backend=BusBackend.KAFKA,
        kafka=KafkaBusSettings(brokers=[]),
    )
    bus = await build_event_bus(settings)
    assert isinstance(bus, InMemoryEventBus)
    await bus.stop()


def test_kafka_bus_settings_trim_empty_brokers() -> None:
    settings = KafkaBusSettings(brokers=["  ", "localhost:1234", ""])
    assert settings.brokers == ["localhost:1234"]


def test_kafka_bus_settings_string_to_list() -> None:
    settings = KafkaBusSettings(brokers="broker-1:9092,  broker-2:9092,,")
    assert settings.brokers == ["broker-1:9092", "broker-2:9092"]


def test_kafka_bus_settings_fallback_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KAFKA_BROKERS", raising=False)
    monkeypatch.setenv("KAFKA_BROKERS", "fallback:9092")
    settings = KafkaBusSettings(brokers=None)
    assert settings.brokers == ["fallback:9092"]
    monkeypatch.delenv("KAFKA_BROKERS", raising=False)


def test_kafka_bus_settings_topic_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KAFKA_TOPIC", raising=False)
    monkeypatch.setenv("KAFKA_TOPIC", "fallback.topic")
    settings = KafkaBusSettings(topic=None)
    assert settings.topic == "fallback.topic"
    monkeypatch.delenv("KAFKA_TOPIC", raising=False)


def test_message_bus_namespace_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUS__NAMESPACE", raising=False)
    monkeypatch.setenv("SERVICE_NAMESPACE", "spooky")
    settings = MessageBusSettings(namespace=None)
    assert settings.namespace == "spooky"
    monkeypatch.delenv("SERVICE_NAMESPACE", raising=False)


def test_message_bus_history_limit_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUS__HISTORY_LIMIT", raising=False)
    monkeypatch.setenv("MONSTER_HISTORY_LIMIT", "321")
    settings = MessageBusSettings(history_limit=None)
    assert settings.history_limit == 321
    monkeypatch.delenv("MONSTER_HISTORY_LIMIT", raising=False)
