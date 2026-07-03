from typing import Any

from src.shared.database import fetch_all_dicts, get_connection, row_to_dict


def listar_productos() -> list[dict[str, Any]]:
    with get_connection() as conn:
        return fetch_all_dicts(
            conn,
            """
            SELECT codigo_articulo, nombre_articulo, precio_unitario, cantidad_existente, activo
            FROM articulos
            ORDER BY codigo_articulo
            """,
        )


def obtener_orden(id_orden: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id_orden,
                   cliente_id,
                   nombre_cliente,
                   ruc_cliente,
                   estado,
                   total_preliminar,
                   motivo_error,
                   correlation_id,
                   reserva_id,
                   numero_factura,
                   cuenta_id,
                   fecha_creacion,
                   fecha_actualizacion
            FROM ordenes
            WHERE id_orden = ?
            """,
            (id_orden,),
        ).fetchone()
        return row_to_dict(row)


def obtener_historial(id_orden: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        return fetch_all_dicts(
            conn,
            """
            SELECT estado, evento, routing_key, correlation_id, message_id, descripcion, fecha
            FROM historial_orden
            WHERE id_orden = ?
            ORDER BY id ASC
            """,
            (id_orden,),
        )
