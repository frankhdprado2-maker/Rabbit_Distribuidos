from typing import Any
from uuid import uuid4

from src.shared.constants import (
    ORDER_STATUS_PENDIENTE,
    ORDER_STATUS_VALIDANDO_STOCK,
    RK_INVENTARIO_VALIDAR,
    SERVICE_ORDENES,
)
from src.shared.database import add_history, get_connection, update_order_status
from src.shared.message_contracts import build_event, utc_now_iso
from src.shared.rabbitmq import declare_topology, get_connection as get_rabbit_connection, publish_event


def _next_order_id(conn) -> str:
    year = "2026"
    row = conn.execute("SELECT COUNT(*) + 1 AS next_id FROM ordenes").fetchone()
    return f"ORD-{year}-{int(row['next_id']):06d}"


def crear_orden(*, cliente_id: str, nombre_cliente: str, ruc_cliente: str, items: list[Any]) -> dict[str, str]:
    if not items:
        raise ValueError("La orden debe incluir al menos un item.")

    for item in items:
        if item.cantidad <= 0:
            raise ValueError("Cada cantidad debe ser mayor que cero.")

    rabbit_connection = get_rabbit_connection()
    rabbit_channel = rabbit_connection.channel()
    declare_topology(rabbit_channel)

    try:
        with get_connection() as conn:
            articulos: list[dict[str, Any]] = []
            total_preliminar = 0.0
            for item in items:
                row = conn.execute(
                    """
                    SELECT codigo_articulo, nombre_articulo, precio_unitario
                    FROM articulos
                    WHERE codigo_articulo = ?
                    """,
                    (item.codigo_articulo,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"El articulo {item.codigo_articulo} no existe.")
                subtotal = float(row["precio_unitario"]) * item.cantidad
                total_preliminar += subtotal
                articulos.append(
                    {
                        "codigo_articulo": row["codigo_articulo"],
                        "nombre_articulo": row["nombre_articulo"],
                        "cantidad": item.cantidad,
                        "precio_unitario": float(row["precio_unitario"]),
                        "subtotal": round(subtotal, 2),
                    }
                )

            id_orden = _next_order_id(conn)
            correlation_id = str(uuid4())
            now = utc_now_iso()

            conn.execute(
                """
                INSERT INTO ordenes (
                    id_orden, cliente_id, nombre_cliente, ruc_cliente, estado,
                    total_preliminar, correlation_id, fecha_creacion, fecha_actualizacion
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    id_orden,
                    cliente_id,
                    nombre_cliente,
                    ruc_cliente,
                    ORDER_STATUS_PENDIENTE,
                    round(total_preliminar, 2),
                    correlation_id,
                    now,
                    now,
                ),
            )

            for articulo in articulos:
                conn.execute(
                    """
                    INSERT INTO detalle_orden (
                        id_orden, codigo_articulo, nombre_articulo, cantidad, precio_unitario, subtotal
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        id_orden,
                        articulo["codigo_articulo"],
                        articulo["nombre_articulo"],
                        articulo["cantidad"],
                        articulo["precio_unitario"],
                        articulo["subtotal"],
                    ),
                )

            event = build_event(
                event_type=RK_INVENTARIO_VALIDAR,
                source=SERVICE_ORDENES,
                id_orden=id_orden,
                correlation_id=correlation_id,
                payload={
                    "cliente": {
                        "cliente_id": cliente_id,
                        "nombre_cliente": nombre_cliente,
                        "ruc_cliente": ruc_cliente,
                    },
                    "items": articulos,
                    "total_preliminar": round(total_preliminar, 2),
                },
            )
            add_history(
                conn,
                id_orden=id_orden,
                estado=ORDER_STATUS_PENDIENTE,
                evento="orden.registrada",
                routing_key=RK_INVENTARIO_VALIDAR,
                correlation_id=correlation_id,
                message_id=event.message_id,
                descripcion="Orden registrada y lista para validacion de inventario.",
            )

            conn.commit()

            publish_event(rabbit_channel, RK_INVENTARIO_VALIDAR, event)
            update_order_status(conn, id_orden=id_orden, estado=ORDER_STATUS_VALIDANDO_STOCK)
            add_history(
                conn,
                id_orden=id_orden,
                estado=ORDER_STATUS_VALIDANDO_STOCK,
                evento=RK_INVENTARIO_VALIDAR,
                routing_key=RK_INVENTARIO_VALIDAR,
                correlation_id=correlation_id,
                message_id=event.message_id,
                descripcion="Mensaje enviado a cola_inventario.",
            )
            conn.commit()

        return {
            "id_orden": id_orden,
            "estado": ORDER_STATUS_VALIDANDO_STOCK,
            "correlation_id": correlation_id,
        }
    finally:
        rabbit_connection.close()
