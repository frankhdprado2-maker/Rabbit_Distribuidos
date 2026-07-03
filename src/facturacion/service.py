from typing import Any

from src.shared.constants import ORDER_STATUS_FACTURADA, RK_CUENTA_CREAR, SERVICE_FACTURACION
from src.shared.database import add_history, already_processed, get_connection, mark_processed, update_order_status
from src.shared.message_contracts import EventEnvelope, build_next_event, utc_now_iso
from src.shared.rabbitmq import publish_event


def _next_invoice_number(conn) -> str:
    row = conn.execute("SELECT COUNT(*) + 1 AS next_id FROM facturas").fetchone()
    return f"F001-{int(row['next_id']):06d}"


def procesar_facturacion(event: EventEnvelope, channel: Any) -> tuple[str, EventEnvelope]:
    if event.event_type != "factura.generar":
        raise ValueError(f"Evento no soportado en facturacion: {event.event_type}")

    with get_connection() as conn:
        if already_processed(conn, event.message_id):
            return "duplicado", event

        factura = conn.execute(
            "SELECT * FROM facturas WHERE id_orden = ?",
            (event.id_orden,),
        ).fetchone()
        if factura is None:
            orden = conn.execute("SELECT * FROM ordenes WHERE id_orden = ?", (event.id_orden,)).fetchone()
            detalle = conn.execute(
                "SELECT SUM(subtotal) AS subtotal FROM detalle_orden WHERE id_orden = ?",
                (event.id_orden,),
            ).fetchone()
            if orden is None:
                raise ValueError(f"Orden no encontrada para facturar: {event.id_orden}")

            subtotal = round(float(detalle["subtotal"] or 0.0), 2)
            total_igv = round(subtotal * 0.18, 2)
            total_factura = round(subtotal + total_igv, 2)
            numero_factura = _next_invoice_number(conn)
            conn.execute(
                """
                INSERT INTO facturas (
                    numero_factura, id_orden, cliente_id, nombre_cliente, ruc_cliente,
                    subtotal, total_igv, total_factura, fecha_emision
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    numero_factura,
                    event.id_orden,
                    orden["cliente_id"],
                    orden["nombre_cliente"],
                    orden["ruc_cliente"],
                    subtotal,
                    total_igv,
                    total_factura,
                    utc_now_iso(),
                ),
            )
            accion = "factura_creada"
        else:
            numero_factura = factura["numero_factura"]
            subtotal = float(factura["subtotal"])
            total_igv = float(factura["total_igv"])
            total_factura = float(factura["total_factura"])
            accion = "factura_existente_reutilizada"

        update_order_status(
            conn,
            id_orden=event.id_orden,
            estado=ORDER_STATUS_FACTURADA,
            numero_factura=numero_factura,
        )
        next_payload = {
            **event.payload,
            "numero_factura": numero_factura,
            "subtotal": subtotal,
            "total_igv": total_igv,
            "total_factura": total_factura,
        }
        next_event = build_next_event(
            event,
            event_type=RK_CUENTA_CREAR,
            source=SERVICE_FACTURACION,
            payload=next_payload,
        )
        publish_event(channel, RK_CUENTA_CREAR, next_event)
        add_history(
            conn,
            id_orden=event.id_orden,
            estado=ORDER_STATUS_FACTURADA,
            evento=RK_CUENTA_CREAR,
            routing_key=RK_CUENTA_CREAR,
            correlation_id=event.correlation_id,
            message_id=next_event.message_id,
            descripcion=f"Factura creada/reutilizada: {numero_factura}.",
        )
        mark_processed(conn, message_id=event.message_id, id_orden=event.id_orden, servicio=SERVICE_FACTURACION)
        conn.commit()
        return accion, next_event
