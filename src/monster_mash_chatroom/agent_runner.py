"""CLI entrypoint for running a monster persona worker."""
from __future__ import annotations

import argparse
import asyncio
import logging
from collections import deque
from collections.abc import Sequence

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import (
    IncompatibleBrokerVersion,
    KafkaError,
    TopicAlreadyExistsError,
    UnknownTopicOrPartitionError,
)

from .config import BusBackend, Settings, get_settings
from .llm import generate_persona_reply
from .models import AuthorKind, ChatMessage
from .personas import PERSONA_REGISTRY, MonsterPersona

logger = logging.getLogger(__name__)


async def _ensure_topic(settings: Settings) -> None:
    bus_settings = settings.bus
    if bus_settings.backend != BusBackend.KAFKA:
        logger.debug("Skipping topic ensure for backend=%s", bus_settings.backend)
        return

    kafka_settings = bus_settings.kafka
    if not kafka_settings.brokers:
        logger.debug("No Kafka brokers configured; skipping topic ensure")
        return
    admin = AIOKafkaAdminClient(bootstrap_servers=kafka_settings.brokers)
    topic = NewTopic(
        name=kafka_settings.topic,
        num_partitions=1,
        replication_factor=1,
    )
    try:
        await admin.create_topics([topic])
        logger.info("Kafka topic '%s' created by worker", kafka_settings.topic)
    except TopicAlreadyExistsError:
        logger.debug(
            "Kafka topic '%s' already exists", kafka_settings.topic
        )
    except IncompatibleBrokerVersion as exc:
        logger.debug(
            "Broker lacks create-topics API; topic must exist already: %s",
            exc,
        )
    except KafkaError as exc:
        logger.warning("Worker failed to ensure topic: %s", exc)
    finally:
        await admin.close()


async def run_persona_worker(
    persona: MonsterPersona, settings: Settings
) -> None:
    """Stream messages for a persona and publish replies when triggered."""
    bus_settings = settings.bus
    if bus_settings.backend != BusBackend.KAFKA:
        logger.warning(
            "Persona %s worker disabled: message bus backend '%s' is not Kafka",
            persona.key,
            bus_settings.backend,
        )
        return

    kafka_settings = bus_settings.kafka
    if not kafka_settings.brokers:
        logger.warning(
            "Persona %s worker disabled: no Kafka brokers configured",
            persona.key,
        )
        return
    producer = AIOKafkaProducer(bootstrap_servers=kafka_settings.brokers)
    consumer = AIOKafkaConsumer(
        kafka_settings.topic,
        bootstrap_servers=kafka_settings.brokers,
        group_id=f"{bus_settings.namespace}.{persona.key}",
        auto_offset_reset="latest",
    )
    await _ensure_topic(settings)

    await producer.start()
    for attempt in range(5):
        try:
            await consumer.start()
            break
        except UnknownTopicOrPartitionError as exc:
            logger.warning(
                "Consumer failed to see topic '%s' (attempt %d/5): %s",
                kafka_settings.topic,
                attempt + 1,
                exc,
            )
            await asyncio.sleep(1)
            await _ensure_topic(settings)
    else:
        logger.error(
            "Persona %s could not subscribe to topic '%s' after retries",
            persona.key,
            kafka_settings.topic,
        )
        await producer.stop()
        return
    logger.info("Worker started for persona=%s", persona.key)
    try:
        backlog = deque[ChatMessage](maxlen=20)
        async for record in consumer:
            payload = record.value.decode("utf-8")
            message = ChatMessage.model_validate_json(payload)
            backlog.append(message)
            if (
                message.role == AuthorKind.MONSTER
                and message.persona == persona.key
            ):
                logger.debug(
                    "Skipping message from identical persona id=%s",
                    message.id,
                )
                continue
            backlog_snapshot = tuple(backlog)
            if not persona.should_respond(message, backlog_snapshot):
                logger.debug(
                    "Persona %s ignoring message id=%s",
                    persona.key,
                    message.id,
                )
                continue
            context = list(backlog)
            read_delay = persona.reading_delay_seconds(
                message, backlog_snapshot
            )
            if read_delay > 0:
                await asyncio.sleep(read_delay)
            reply = await generate_persona_reply(
                persona,
                context,
                settings,
            )
            response = ChatMessage(
                author=persona.display_name,
                role=AuthorKind.MONSTER,
                persona=persona.key,
                content=reply,
                persona_emoji=persona.emoji or None,
            )
            typing_delay = persona.typing_delay_seconds(reply)
            if typing_delay > 0:
                await asyncio.sleep(typing_delay)
            await producer.send_and_wait(
                kafka_settings.topic,
                response.model_dump_json().encode("utf-8"),
            )
            logger.info(
                "%s replied to %s",
                persona.display_name,
                message.author,
            )
    finally:
        await consumer.stop()
        await producer.stop()
        logger.info("Worker stopped for persona=%s", persona.key)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a monster persona worker"
    )
    parser.add_argument("persona", choices=sorted(PERSONA_REGISTRY.keys()))
    return parser.parse_args(argv)


async def main_async(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    settings = get_settings()
    persona = PERSONA_REGISTRY[args.persona]
    await run_persona_worker(persona, settings)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
