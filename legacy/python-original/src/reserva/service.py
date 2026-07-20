from typing import Any
from uuid import uuid4

from src.shared.constants import (
    ORDER_STATUS_RESERVADA,
    RK_FACTURA_GENERAR,
    RK_ORDEN_ERROR,
    SERVICE_RESERVA,
)
from src.shared.database import add_history, already_processed, get_connection, mark_processed, update_order_status
from src.shared.message_contracts import EventEnvelope, build_next_event, utc_now_iso
from src.shared.rabbitmq import publish_event


def _stock_error(event: EventEnvelope, details: list[dict[str, Any]]) -> EventEnvelope:
    return build_next_event(
        event,
        event_type=RK_ORDEN_ERROR,
        source=SERVICE_RESERVA,
        payload={
            "error_type": "BUSINESS",
            "error_code": "STOCK_INSUFICIENTE",
            "message": "No existe stock suficiente para completar la orden.",
            "details": details,
            "retryable": False,
        },
    )


def procesar_reserva(event: EventEnvelope, channel: Any) -> tuple[str, EventEnvelope]:
    if event.event_type != "reserva.crear":
        raise ValueError(f"Evento no soportado en reserva: {event.event_type}")

    with get_connection() as conn:
        if already_processed(conn, event.message_id):
            return "duplicado", event

        row = conn.execute("SELECT id_reserva FROM reservas WHERE id_orden = ?", (event.id_orden,)).fetchone()
        if row is None:
            details: list[dict[str, Any]] = []
            for item in event.payload.get("items", []):
                row_articulo = conn.execute(
                    "SELECT cantidad_existente FROM articulos WHERE codigo_articulo = ?",
                    (item["codigo_articulo"],),
                ).fetchone()
                stock_actual = int(row_articulo["cantidad_existente"]) if row_articulo else 0
                solicitado = int(item["cantidad"])
                if stock_actual - solicitado < 0:
                    details.append(
                        {
                            "codigo_articulo": item["codigo_articulo"],
                            "stock_actual": stock_actual,
                            "cantidad_solicitada": solicitado,
                        }
                    )

            if details:
                next_event = _stock_error(event, details)
                publish_event(channel, RK_ORDEN_ERROR, next_event)
                add_history(
                    conn,
                    id_orden=event.id_orden,
                    estado=ORDER_STATUS_RESERVADA,
                    evento=RK_ORDEN_ERROR,
                    routing_key=RK_ORDEN_ERROR,
                    correlation_id=event.correlation_id,
                    message_id=next_event.message_id,
                    descripcion="Reserva rechazo la orden para evitar stock negativo.",
                )
                mark_processed(conn, message_id=event.message_id, id_orden=event.id_orden, servicio=SERVICE_RESERVA)
                conn.commit()
                return "rechazo_publicado", next_event

            id_reserva = f"RES-{uuid4().hex[:10].upper()}"
            for item in event.payload.get("items", []):
                conn.execute(
                    """
                    UPDATE articulos
                    SET cantidad_existente = cantidad_existente - ?
                    WHERE codigo_articulo = ? AND cantidad_existente >= ?
                    """,
                    (int(item["cantidad"]), item["codigo_articulo"], int(item["cantidad"])),
                )
            conn.execute(
                """
                INSERT INTO reservas (id_reserva, id_orden, estado_reserva, fecha_reserva)
                VALUES (?, ?, ?, ?)
                """,
                (id_reserva, event.id_orden, "ACTIVA", utc_now_iso()),
            )
            accion = "stock_descontado_reserva_creada"
        else:
            id_reserva = row["id_reserva"]
            accion = "reserva_existente_reutilizada"

        update_order_status(conn, id_orden=event.id_orden, estado=ORDER_STATUS_RESERVADA, reserva_id=id_reserva)
        next_payload = {**event.payload, "reserva_id": id_reserva}
        next_event = build_next_event(
            event,
            event_type=RK_FACTURA_GENERAR,
            source=SERVICE_RESERVA,
            payload=next_payload,
        )
        publish_event(channel, RK_FACTURA_GENERAR, next_event)
        add_history(
            conn,
            id_orden=event.id_orden,
            estado=ORDER_STATUS_RESERVADA,
            evento=RK_FACTURA_GENERAR,
            routing_key=RK_FACTURA_GENERAR,
            correlation_id=event.correlation_id,
            message_id=next_event.message_id,
            descripcion=f"Reserva creada/reutilizada: {id_reserva}.",
        )
        mark_processed(conn, message_id=event.message_id, id_orden=event.id_orden, servicio=SERVICE_RESERVA)
        conn.commit()
        return accion, next_event
