import json
import logging
import time
import threading

import pika

from classifier import run_classifier
from normalizer import run_normalizer
from graphs.neo4j_client import GraphClient
from runtime_config import rabbitmq_url

from database import get_message_by_id, update_message_status, save_opportunities


RABBITMQ_URL = rabbitmq_url()
LOGGER = logging.getLogger(__name__)

# Score mínimo para envio de oportunidades de parceiros
MIN_MATCH_SCORE = 50


def _is_self_opportunity(opp: dict) -> bool:
    """Identifica se a oportunidade envolve imóvel próprio do inventário Majesto."""
    if opp.get("is_self") is True:
        return True
    offer_id = str(opp.get("offer_id") or "")
    if offer_id.startswith("self-offer:"):
        return True
    seller = opp.get("seller") or {}
    seller_id = str(seller.get("person_id") or seller.get("id") or "")
    return seller_id == "system:majesto"


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

    # Qualificação de oportunidades no Engine:
    # - Imóveis próprios Majesto têm prioridade máxima e passam direto.
    # - Oportunidades de parceiros exigem score > 50; scores <= 50 são descartadas e logadas aqui no Engine.
    qualified_opportunities = []
    for opp in opportunities:
        score = opp.get("score")
        is_self = _is_self_opportunity(opp)
        opp["is_self"] = is_self
        if score is not None and not is_self and score <= MIN_MATCH_SCORE:
            LOGGER.info(
                "oportunidade de parceiro descartada por score insuficiente (score=%s <= %s): demand=%s offer=%s",
                score,
                MIN_MATCH_SCORE,
                opp.get("demand_id"),
                opp.get("offer_id"),
            )
            continue
        qualified_opportunities.append(opp)

    published_count = 0
    if qualified_opportunities:
        opp_ids = save_opportunities(qualified_opportunities)
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
        "message processed successfully message_id=%s opportunities=%s (qualificadas=%s)",
        message_id,
        len(opportunities),
        published_count,
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
        redelivered = getattr(method, "redelivered", False)
        LOGGER.error(
            "message processing failed message_id=%s error=%s (redelivered=%s)",
            msg_id,
            type(exc).__name__,
            redelivered,
        )
        if redelivered:
            LOGGER.critical(
                "poison message detected message_id=%s after retry: descartando da fila para evitar loop infinito",
                msg_id,
            )
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return False

        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        return False

    ch.basic_ack(delivery_tag=method.delivery_tag)
    return True


def _cleaner_loop(interval_hours: int = 6):
    """Executa a limpeza periódica do Neo4j e PostgreSQL em segundo plano."""
    from cleaner import run_cleaner
    interval_seconds = interval_hours * 3600
    while True:
        try:
            LOGGER.info("iniciando ciclo periódico do cleaner")
            run_cleaner()
            LOGGER.info("ciclo do cleaner concluído com sucesso")
        except Exception as exc:
            LOGGER.error("erro durante execução do cleaner: %s", exc)
        time.sleep(interval_seconds)


def start_cleaner_daemon(interval_hours: int = 6):
    thread = threading.Thread(target=_cleaner_loop, args=(interval_hours,), daemon=True)
    thread.start()
    LOGGER.info("cleaner daemon iniciado (intervalo: %dh)", interval_hours)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    LOGGER.info("connecting to RabbitMQ")
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()

    channel.queue_declare(queue="raw_messages", durable=True)
    channel.queue_declare(queue="opportunities_queue", durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue="raw_messages", on_message_callback=on_message)

    # Inicia a faxina periódica (90d ofertas / 15d demandas / órfãos)
    start_cleaner_daemon(interval_hours=6)

    LOGGER.info("engine worker active")
    channel.start_consuming()


if __name__ == "__main__":
    main()
