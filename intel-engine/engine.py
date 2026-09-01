import json
import logging

import pika

from classifier import run_classifier
from normalizer import run_normalizer
from graphs.neo4j_client import GraphClient
from runtime_config import rabbitmq_url

from database import get_message_by_id, update_message_status, save_opportunities


RABBITMQ_URL = rabbitmq_url()
LOGGER = logging.getLogger(__name__)


def process_message(message_id, publish_opportunity):
    """Process one message without making delivery-level ACK/NACK decisions."""
    msg_data = get_message_by_id(message_id)
    if not msg_data:
        raise LookupError(f"raw message {message_id} not found in PostgreSQL")

    if msg_data.get("status") == "PROCESSED":
        LOGGER.info("message already processed message_id=%s", message_id)
        return {"already_processed": True, "opportunities": 0}

    sellers, buyers, useless = run_classifier([msg_data])
    sellers_pad, buyers_pad = run_normalizer(sellers, buyers)

    graph = GraphClient()
    try:
        for ad in sellers_pad + buyers_pad:
            graph.ingest_ad(ad)
        # An empty result is a valid successful match evaluation.
        opportunities = graph.match_opportunities()
    finally:
        graph.close()

    published_count = 0
    if opportunities:
        opp_ids = save_opportunities(opportunities)
        for opp_id in opp_ids:
            publish_opportunity(opp_id)
            published_count += 1

    pad_data_map = {
        ad["original_content"]["message_id"]: ad
        for ad in sellers_pad + buyers_pad
    }
    norm_data = pad_data_map.get(message_id)
    update_message_status(message_id, "PROCESSED", normalized_data=norm_data)
    LOGGER.info(
        "message processed successfully message_id=%s opportunities=%s",
        message_id,
        len(opportunities),
    )
    return {"already_processed": False, "opportunities": published_count}


def _publish_opportunity(channel, opportunity_id):
    channel.basic_publish(
        exchange="",
        routing_key="opportunities_queue",
        body=json.dumps({"opportunity_id": opportunity_id}),
        properties=pika.BasicProperties(delivery_mode=2),
    )


def on_message(ch, method, properties, body):
    """RabbitMQ delivery callback with mutually exclusive ACK/NACK outcomes."""
    msg_id = None
    try:
        event_data = json.loads(body)
        msg_id = event_data.get("message_id")
        if not msg_id:
            raise ValueError("raw_messages event missing message_id")

        process_message(msg_id, lambda opp_id: _publish_opportunity(ch, opp_id))
    except Exception as exc:
        LOGGER.error(
            "message processing failed message_id=%s error=%s",
            msg_id,
            type(exc).__name__,
        )
        # Retryable at-least-once behavior; DLQ policy is a later task.
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        return False

    ch.basic_ack(delivery_tag=method.delivery_tag)
    return True


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    LOGGER.info("connecting to RabbitMQ")
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()

    channel.queue_declare(queue="raw_messages", durable=True)
    channel.queue_declare(queue="opportunities_queue", durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue="raw_messages", on_message_callback=on_message)

    LOGGER.info("engine worker active")
    channel.start_consuming()


if __name__ == "__main__":
    main()
