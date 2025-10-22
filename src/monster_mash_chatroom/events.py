"""Infrastructure that fans chat messages to Kafka and WebSocket clients."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import deque
from collections.abc import AsyncGenerator

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import (
    IncompatibleBrokerVersion,
    KafkaConnectionError,
    KafkaError,
    TopicAlreadyExistsError,
)

from .config import BusBackend, KafkaBusSettings, MessageBusSettings
from .models import ChatMessage

logger = logging.getLogger(__name__)


class EventBus:
    """Abstract interface for publishing and subscribing to chat messages."""

    async def start(self) -> None:  # pragma: no cover - interface hook
        raise NotImplementedError

    async def stop(self) -> None:  # pragma: no cover - interface hook
        raise NotImplementedError

    async def publish(self, message: ChatMessage) -> None:  # pragma: no cover
        raise NotImplementedError

    async def subscribe(self) -> AsyncGenerator[ChatMessage, None]:
        raise NotImplementedError

    async def get_recent(self) -> list[ChatMessage]:  # pragma: no cover
        raise NotImplementedError


class InMemoryEventBus(EventBus):
    """Fallback event bus when Kafka is unavailable."""

    def __init__(self, history_limit: int = 200):
        self._history: deque[ChatMessage] = deque(maxlen=history_limit)
        self._subscribers: set[asyncio.Queue[ChatMessage]] = set()

    async def start(self) -> None:
        logger.warning(
            "Starting InMemoryEventBus – Kafka connection unavailable"
        )

    async def stop(self) -> None:
        self._subscribers.clear()
        logger.debug("InMemoryEventBus cleared subscribers on shutdown")

    async def publish(self, message: ChatMessage) -> None:
        self._history.append(message)
        dead: list[asyncio.Queue[ChatMessage]] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                dead.append(queue)
        if dead:
            logger.debug("Pruned %d slow subscribers", len(dead))
        for queue in dead:
            self._subscribers.discard(queue)

    async def subscribe(self) -> AsyncGenerator[ChatMessage, None]:
        queue: asyncio.Queue[ChatMessage] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)
            logger.debug("Subscriber removed from in-memory bus")

    async def get_recent(self) -> list[ChatMessage]:
        return list(self._history)


class KafkaEventBus(EventBus):
    """Kafka-backed event bus providing fan-out to WebSocket clients."""

    def __init__(
        self,
        settings: KafkaBusSettings,
        namespace: str,
        history_limit: int,
    ) -> None:
        self._settings = settings
        self._namespace = namespace
        self._producer: AIOKafkaProducer | None = None
        self._consumer: AIOKafkaConsumer | None = None
        self._consumer_task: asyncio.Task[None] | None = None
        self._history: deque[ChatMessage] = deque(maxlen=history_limit)
        self._subscriber_queues: set[asyncio.Queue[ChatMessage]] = set()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        logger.info(
            "Starting KafkaEventBus – brokers=%s", self._settings.brokers
        )
        try:
            await asyncio.wait_for(self._ensure_topic(), timeout=10)
        except asyncio.TimeoutError as exc:
            raise KafkaConnectionError(
                "Timed out while ensuring Kafka topic"
            ) from exc
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._settings.brokers
        )
        try:
            await asyncio.wait_for(self._producer.start(), timeout=10)
        except (asyncio.TimeoutError, KafkaError, KafkaConnectionError) as exc:
            await self._producer.stop()
            self._producer = None
            raise KafkaConnectionError(
                "Failed to start Kafka producer"
            ) from exc
        self._consumer = AIOKafkaConsumer(
            self._settings.topic,
            bootstrap_servers=self._settings.brokers,
            group_id=f"{self._namespace}.websocket-relay",
            enable_auto_commit=True,
            auto_offset_reset="latest",
        )
        try:
            await asyncio.wait_for(self._consumer.start(), timeout=10)
        except (asyncio.TimeoutError, KafkaError, KafkaConnectionError) as exc:
            await self._consumer.stop()
            self._consumer = None
            if self._producer is not None:
                await self._producer.stop()
                self._producer = None
            raise KafkaConnectionError(
                "Failed to start Kafka consumer"
            ) from exc
        self._consumer_task = asyncio.create_task(self._consume_loop())

    async def stop(self) -> None:
        if self._consumer_task:
            self._consumer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consumer_task
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
        if self._producer:
            await self._producer.stop()
            self._producer = None
        self._subscriber_queues.clear()

    async def publish(self, message: ChatMessage) -> None:
        if not self._producer:
            raise RuntimeError("KafkaEventBus not started")
        payload = message.model_dump(mode="json")
        await self._producer.send_and_wait(
            self._settings.topic,
            json.dumps(payload).encode("utf-8"),
        )
        logger.debug(
            "KafkaEventBus published message id=%s persona=%s",
            message.id,
            message.persona,
        )

    async def subscribe(self) -> AsyncGenerator[ChatMessage, None]:
        queue: asyncio.Queue[ChatMessage] = asyncio.Queue()
        async with self._lock:
            self._subscriber_queues.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            async with self._lock:
                self._subscriber_queues.discard(queue)
        logger.debug("Subscriber removed from Kafka fan-out queue")

    async def get_recent(self) -> list[ChatMessage]:
        return list(self._history)

    async def _consume_loop(self) -> None:
        assert self._consumer is not None
        async for record in self._consumer:
            try:
                payload = json.loads(record.value.decode("utf-8"))
                message = ChatMessage.model_validate(payload)
            except ValueError as exc:
                logger.exception(
                    "Failed to decode chat message", exc_info=exc
                )
                continue
            self._history.append(message)
            await self._fan_out(message)
            logger.debug(
                "KafkaEventBus consumed message id=%s persona=%s",
                message.id,
                message.persona,
            )

    async def _fan_out(self, message: ChatMessage) -> None:
        async with self._lock:
            queues = list(self._subscriber_queues)
        dead: list[asyncio.Queue[ChatMessage]] = []
        for queue in queues:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                dead.append(queue)
        if dead:
            async with self._lock:
                for queue in dead:
                    if queue in self._subscriber_queues:
                        self._subscriber_queues.remove(queue)
            logger.debug("Removed %d back-pressured queues", len(dead))

    async def _ensure_topic(self) -> None:
        """Create the Kafka topic when it does not already exist."""

        admin = AIOKafkaAdminClient(bootstrap_servers=self._settings.brokers)
        topic = NewTopic(
            name=self._settings.topic,
            num_partitions=1,
            replication_factor=1,
        )
        try:
            await admin.create_topics([topic])
            logger.info("Created Kafka topic '%s'", self._settings.topic)
        except TopicAlreadyExistsError:
            logger.debug(
                "Kafka topic '%s' already exists", self._settings.topic
            )
        except IncompatibleBrokerVersion as exc:
            logger.warning(
                "Kafka broker lacks create-topics API; "
                "relying on auto-create: %s",
                exc,
            )
        except KafkaError as exc:
            logger.error("Failed to ensure Kafka topic: %s", exc)
            raise
        finally:
            await admin.close()


async def build_event_bus(settings: MessageBusSettings) -> EventBus:
    """Create the configured event bus, with Kafka or in-memory fallback."""

    if settings.backend == BusBackend.IN_MEMORY:
        bus = InMemoryEventBus(settings.history_limit)
        await bus.start()
        logger.info("Using in-memory event bus")
        return bus

    if settings.backend == BusBackend.KAFKA:
        kafka_settings = settings.kafka
        if not kafka_settings.brokers:
            logger.warning(
                "Kafka backend selected without brokers; using in-memory bus"
            )
            fallback = InMemoryEventBus(settings.history_limit)
            await fallback.start()
            return fallback

        bus = KafkaEventBus(
            kafka_settings,
            namespace=settings.namespace,
            history_limit=settings.history_limit,
        )
        try:
            await bus.start()
            logger.info(
                "Connected to Kafka brokers %s", kafka_settings.brokers
            )
            return bus
        except (KafkaConnectionError, KafkaError, OSError) as exc:
            logger.warning(
                "Kafka connection failed (%s); using in-memory bus",
                exc,
            )
            fallback = InMemoryEventBus(settings.history_limit)
            await fallback.start()
            return fallback

    raise ValueError(f"Unsupported message bus backend: {settings.backend}")
