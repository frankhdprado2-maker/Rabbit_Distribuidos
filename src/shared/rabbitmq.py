import json
import time
from collections.abc import Callable
from typing import Any

import pika

from src.shared.config import get_settings
from src.shared.constants import (
    CONTENT_TYPE_JSON,
    DLX_NAME,
    EXCHANGE_NAME,
    QUEUE_CXC,
    QUEUE_ERRORES,
    QUEUE_FACTURACION,
    QUEUE_INVENTARIO,
    QUEUE_RESERVA,
    QUEUE_RESPUESTA,
    RK_CUENTA_CREAR,
    RK_ERROR_TECNICO,
    RK_FACTURA_GENERAR,
    RK_INVENTARIO_VALIDAR,
    RK_ORDEN_CONFIRMAR,
    RK_ORDEN_ERROR,
    RK_RESERVA_CREAR,
)
from src.shared.message_contracts import EventEnvelope


QUEUE_BINDINGS = {
    QUEUE_INVENTARIO: [RK_INVENTARIO_VALIDAR],
    QUEUE_RESERVA: [RK_RESERVA_CREAR],
    QUEUE_FACTURACION: [RK_FACTURA_GENERAR],
    QUEUE_CXC: [RK_CUENTA_CREAR],
    QUEUE_RESPUESTA: [RK_ORDEN_CONFIRMAR, RK_ORDEN_ERROR],
    QUEUE_ERRORES: [RK_ERROR_TECNICO],
}


def get_connection(retries: int = 12, delay_seconds: float = 2.0) -> pika.BlockingConnection:
    settings = get_settings()
    credentials = pika.PlainCredentials(settings.rabbitmq_user, settings.rabbitmq_password)
    parameters = pika.ConnectionParameters(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        virtual_host=settings.rabbitmq_vhost,
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=30,
    )

    last_error: Exception | None = None
    for _ in range(retries):
        try:
            return pika.BlockingConnection(parameters)
        except pika.exceptions.AMQPConnectionError as exc:
            last_error = exc
            time.sleep(delay_seconds)

    raise RuntimeError(f"No se pudo conectar a RabbitMQ: {last_error}") from last_error


def declare_topology(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type="direct", durable=True)
    channel.exchange_declare(exchange=DLX_NAME, exchange_type="direct", durable=True)

    for queue_name, routing_keys in QUEUE_BINDINGS.items():
        arguments: dict[str, Any] | None = None
        if queue_name != QUEUE_ERRORES:
            arguments = {
                "x-dead-letter-exchange": DLX_NAME,
                "x-dead-letter-routing-key": RK_ERROR_TECNICO,
            }
        channel.queue_declare(queue=queue_name, durable=True, arguments=arguments)
        for routing_key in routing_keys:
            exchange = DLX_NAME if routing_key == RK_ERROR_TECNICO else EXCHANGE_NAME
            channel.queue_bind(queue=queue_name, exchange=exchange, routing_key=routing_key)


def publish_event(
    channel: pika.adapters.blocking_connection.BlockingChannel,
    routing_key: str,
    event: EventEnvelope,
) -> None:
    body = json.dumps(event.model_dump(), ensure_ascii=False).encode("utf-8")
    channel.basic_publish(
        exchange=EXCHANGE_NAME,
        routing_key=routing_key,
        body=body,
        properties=pika.BasicProperties(
            content_type=CONTENT_TYPE_JSON,
            delivery_mode=2,
            correlation_id=event.correlation_id,
            message_id=event.message_id,
        ),
        mandatory=False,
    )


def publish_error_tecnico(
    channel: pika.adapters.blocking_connection.BlockingChannel,
    event: EventEnvelope,
) -> None:
    body = json.dumps(event.model_dump(), ensure_ascii=False).encode("utf-8")
    channel.basic_publish(
        exchange=DLX_NAME,
        routing_key=RK_ERROR_TECNICO,
        body=body,
        properties=pika.BasicProperties(
            content_type=CONTENT_TYPE_JSON,
            delivery_mode=2,
            correlation_id=event.correlation_id,
            message_id=event.message_id,
        ),
    )


def start_consumer(
    *,
    queue_name: str,
    callback: Callable[..., None],
) -> None:
    connection = get_connection()
    channel = connection.channel()
    declare_topology(channel)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=False)
    channel.start_consuming()
