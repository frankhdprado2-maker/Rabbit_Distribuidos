import json
from typing import Any

from pydantic import ValidationError

from src.shared.constants import (
    ORDER_STATUS_CONFIRMADA,
    ORDER_STATUS_ERROR,
    ORDER_STATUS_RECHAZADA,
    QUEUE_RESPUESTA,
    RK_ORDEN_CONFIRMAR,
    RK_ORDEN_ERROR,
    SERVICE_ORDENES,
)
from src.shared.database import add_history, already_processed, get_connection, mark_processed, update_order_status
from src.shared.logging_utils import configure_logging
from src.shared.message_contracts import EventEnvelope
from src.shared.rabbitmq import declare_topology, get_connection as get_rabbit_connection


logger = configure_logging(SERVICE_ORDENES)


def _handle_event(event: EventEnvelope, routing_key: str) -> None:
    with get_connection() as conn:
        if already_processed(conn, event.message_id):
            logger.info("Mensaje duplicado ignorado id_orden=%s message_id=%s", event.id_orden, event.message_id)
            return

        if event.event_type == RK_ORDEN_CONFIRMAR:
            update_order_status(
                conn,
                id_orden=event.id_orden,
                estado=ORDER_STATUS_CONFIRMADA,
                reserva_id=event.payload.get("reserva_id"),
                numero_factura=event.payload.get("numero_factura"),
                cuenta_id=event.payload.get("cuenta_id"),
            )
            add_history(
                conn,
                id_orden=event.id_orden,
                estado=ORDER_STATUS_CONFIRMADA,
                evento=event.event_type,
                routing_key=routing_key,
                correlation_id=event.correlation_id,
                message_id=event.message_id,
                descripcion="Orden confirmada con reserva, factura y cuenta por cobrar.",
            )
            logger.info("Orden confirmada id_orden=%s correlation_id=%s", event.id_orden, event.correlation_id)
        elif event.event_type == RK_ORDEN_ERROR:
            error_type = event.payload.get("error_type", "TECHNICAL")
            estado = ORDER_STATUS_RECHAZADA if error_type == "BUSINESS" else ORDER_STATUS_ERROR
            motivo_error = event.payload.get("message", "Error no especificado.")
            update_order_status(conn, id_orden=event.id_orden, estado=estado, motivo_error=motivo_error)
            add_history(
                conn,
                id_orden=event.id_orden,
                estado=estado,
                evento=event.event_type,
                routing_key=routing_key,
                correlation_id=event.correlation_id,
                message_id=event.message_id,
                descripcion=motivo_error,
            )
            logger.info(
                "Orden con error id_orden=%s correlation_id=%s error_type=%s",
                event.id_orden,
                event.correlation_id,
                error_type,
            )
        else:
            raise ValueError(f"Evento no soportado en cola_respuesta: {event.event_type}")

        mark_processed(conn, message_id=event.message_id, id_orden=event.id_orden, servicio=SERVICE_ORDENES)
        conn.commit()


def callback(ch: Any, method: Any, properties: Any, body: bytes) -> None:
    try:
        data = json.loads(body.decode("utf-8"))
        event = EventEnvelope.model_validate(data)
        logger.info(
            "Mensaje recibido cola=%s id_orden=%s correlation_id=%s routing_key=%s",
            QUEUE_RESPUESTA,
            event.id_orden,
            event.correlation_id,
            method.routing_key,
        )
        _handle_event(event, method.routing_key)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        logger.info("ACK enviado id_orden=%s message_id=%s", event.id_orden, event.message_id)
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        logger.exception("Error detectado en consumidor de respuestas: %s", exc)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def main() -> None:
    logger.info("Servicio iniciado. Cola consumida: %s", QUEUE_RESPUESTA)
    connection = get_rabbit_connection()
    channel = connection.channel()
    declare_topology(channel)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_RESPUESTA, on_message_callback=callback, auto_ack=False)
    channel.start_consuming()


if __name__ == "__main__":
    main()
