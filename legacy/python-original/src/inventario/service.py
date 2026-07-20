from typing import Any

from src.shared.constants import (
    ORDER_STATUS_VALIDANDO_STOCK,
    RK_ORDEN_ERROR,
    RK_RESERVA_CREAR,
    SERVICE_INVENTARIO,
)
from src.shared.database import add_history, already_processed, get_connection, mark_processed
from src.shared.message_contracts import EventEnvelope, build_next_event
from src.shared.rabbitmq import publish_event


def _business_error(event: EventEnvelope, details: list[dict[str, Any]]) -> EventEnvelope:
    return build_next_event(
        event,
        event_type=RK_ORDEN_ERROR,
        source=SERVICE_INVENTARIO,
        payload={
            "error_type": "BUSINESS",
            "error_code": "STOCK_INSUFICIENTE",
            "message": "No existe stock suficiente para completar la orden.",
            "details": details,
            "retryable": False,
        },
    )


def procesar_validacion(event: EventEnvelope, channel: Any) -> tuple[str, EventEnvelope]:
    if event.event_type != "inventario.validar":
        raise ValueError(f"Evento no soportado en inventario: {event.event_type}")

    with get_connection() as conn:
        if already_processed(conn, event.message_id):
            return "duplicado", event

        details: list[dict[str, Any]] = []
        for item in event.payload.get("items", []):
            codigo = item["codigo_articulo"]
            solicitado = int(item["cantidad"])
            row = conn.execute(
                """
                SELECT codigo_articulo, nombre_articulo, cantidad_existente, activo
                FROM articulos
                WHERE codigo_articulo = ?
                """,
                (codigo,),
            ).fetchone()
            if row is None:
                details.append({"codigo_articulo": codigo, "motivo": "PRODUCTO_NO_EXISTE"})
                continue
            if int(row["activo"]) != 1:
                details.append({"codigo_articulo": codigo, "motivo": "PRODUCTO_INACTIVO"})
                continue
            if int(row["cantidad_existente"]) < solicitado:
                details.append(
                    {
                        "codigo_articulo": codigo,
                        "motivo": "STOCK_INSUFICIENTE",
                        "stock_actual": int(row["cantidad_existente"]),
                        "cantidad_solicitada": solicitado,
                    }
                )

        if details:
            next_event = _business_error(event, details)
            publish_event(channel, RK_ORDEN_ERROR, next_event)
            add_history(
                conn,
                id_orden=event.id_orden,
                estado=ORDER_STATUS_VALIDANDO_STOCK,
                evento=RK_ORDEN_ERROR,
                routing_key=RK_ORDEN_ERROR,
                correlation_id=event.correlation_id,
                message_id=next_event.message_id,
                descripcion="Inventario rechazo la orden por stock o articulo invalido.",
            )
            accion = "rechazo_publicado"
        else:
            next_event = build_next_event(
                event,
                event_type=RK_RESERVA_CREAR,
                source=SERVICE_INVENTARIO,
                payload=event.payload,
            )
            publish_event(channel, RK_RESERVA_CREAR, next_event)
            add_history(
                conn,
                id_orden=event.id_orden,
                estado=ORDER_STATUS_VALIDANDO_STOCK,
                evento=RK_RESERVA_CREAR,
                routing_key=RK_RESERVA_CREAR,
                correlation_id=event.correlation_id,
                message_id=next_event.message_id,
                descripcion="Inventario valido stock suficiente y envio solicitud de reserva.",
            )
            accion = "reserva_publicada"

        mark_processed(conn, message_id=event.message_id, id_orden=event.id_orden, servicio=SERVICE_INVENTARIO)
        conn.commit()
        return accion, next_event
