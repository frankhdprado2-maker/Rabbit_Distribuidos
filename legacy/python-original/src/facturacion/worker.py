import json
from typing import Any

from pydantic import ValidationError

from src.facturacion.service import procesar_facturacion
from src.shared.constants import QUEUE_FACTURACION, SERVICE_FACTURACION
from src.shared.logging_utils import configure_logging
from src.shared.message_contracts import EventEnvelope
from src.shared.rabbitmq import declare_topology, get_connection as get_rabbit_connection


logger = configure_logging(SERVICE_FACTURACION)


def callback(ch: Any, method: Any, properties: Any, body: bytes) -> None:
    try:
        event = EventEnvelope.model_validate(json.loads(body.decode("utf-8")))
        logger.info(
            "Mensaje recibido cola=%s id_orden=%s correlation_id=%s routing_key=%s",
            QUEUE_FACTURACION,
            event.id_orden,
            event.correlation_id,
            method.routing_key,
        )
        accion, next_event = procesar_facturacion(event, ch)
        logger.info("Accion realizada=%s mensaje_publicado=%s", accion, next_event.event_type)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        logger.info("ACK enviado id_orden=%s message_id=%s", event.id_orden, event.message_id)
    except (json.JSONDecodeError, ValidationError, ValueError, KeyError) as exc:
        logger.exception("Error detectado en facturacion: %s", exc)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def main() -> None:
    logger.info("Servicio iniciado. Cola consumida: %s", QUEUE_FACTURACION)
    connection = get_rabbit_connection()
    channel = connection.channel()
    declare_topology(channel)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_FACTURACION, on_message_callback=callback, auto_ack=False)
    channel.start_consuming()


if __name__ == "__main__":
    main()
