from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from src.shared.constants import (
    ORDER_STATUS_CUENTA_CREADA,
    RK_ORDEN_CONFIRMAR,
    SERVICE_CXC,
)
from src.shared.database import add_history, already_processed, get_connection, mark_processed, update_order_status
from src.shared.message_contracts import EventEnvelope, build_next_event
from src.shared.rabbitmq import publish_event


def procesar_cuenta(event: EventEnvelope, channel: Any) -> tuple[str, EventEnvelope]:
    if event.event_type != "cuenta.crear":
        raise ValueError(f"Evento no soportado en cuentas por cobrar: {event.event_type}")

    numero_factura = event.payload.get("numero_factura")
    if not numero_factura:
        raise ValueError("El mensaje no incluye numero_factura.")

    with get_connection() as conn:
        if already_processed(conn, event.message_id):
            return "duplicado", event

        cuenta = conn.execute(
            "SELECT * FROM cuentas_cobrar WHERE numero_factura = ?",
            (numero_factura,),
        ).fetchone()
        if cuenta is None:
            factura = conn.execute("SELECT * FROM facturas WHERE numero_factura = ?", (numero_factura,)).fetchone()
            if factura is None:
                raise ValueError(f"Factura no encontrada para cuenta por cobrar: {numero_factura}")
            id_cuenta = f"CXC-{uuid4().hex[:10].upper()}"
            fecha_cobro = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
            conn.execute(
                """
                INSERT INTO cuentas_cobrar (
                    id_cuenta, numero_factura, cliente_id, nombre_cliente, ruc_cliente,
                    total_cobrar, fecha_cobro, estado_registro
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    id_cuenta,
                    numero_factura,
                    factura["cliente_id"],
                    factura["nombre_cliente"],
                    factura["ruc_cliente"],
                    float(factura["total_factura"]),
                    fecha_cobro,
                    "PENDIENTE",
                ),
            )
            total_cobrar = float(factura["total_factura"])
            accion = "cuenta_creada"
        else:
            id_cuenta = cuenta["id_cuenta"]
            total_cobrar = float(cuenta["total_cobrar"])
            accion = "cuenta_existente_reutilizada"

        update_order_status(conn, id_orden=event.id_orden, estado=ORDER_STATUS_CUENTA_CREADA, cuenta_id=id_cuenta)
        next_payload = {
            **event.payload,
            "cuenta_id": id_cuenta,
            "total_cobrar": total_cobrar,
        }
        next_event = build_next_event(
            event,
            event_type=RK_ORDEN_CONFIRMAR,
            source=SERVICE_CXC,
            payload=next_payload,
        )
        publish_event(channel, RK_ORDEN_CONFIRMAR, next_event)
        add_history(
            conn,
            id_orden=event.id_orden,
            estado=ORDER_STATUS_CUENTA_CREADA,
            evento=RK_ORDEN_CONFIRMAR,
            routing_key=RK_ORDEN_CONFIRMAR,
            correlation_id=event.correlation_id,
            message_id=next_event.message_id,
            descripcion=f"Cuenta por cobrar creada/reutilizada: {id_cuenta}.",
        )
        mark_processed(conn, message_id=event.message_id, id_orden=event.id_orden, servicio=SERVICE_CXC)
        conn.commit()
        return accion, next_event
