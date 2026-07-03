from src.shared.database import fetch_all_dicts, get_connection


def obtener_detalle_orden(id_orden: str) -> list[dict]:
    with get_connection() as conn:
        return fetch_all_dicts(
            conn,
            """
            SELECT codigo_articulo, nombre_articulo, cantidad, precio_unitario, subtotal
            FROM detalle_orden
            WHERE id_orden = ?
            ORDER BY id ASC
            """,
            (id_orden,),
        )
