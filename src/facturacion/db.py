from src.shared.database import row_to_dict, get_connection


def obtener_factura_por_orden(id_orden: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM facturas WHERE id_orden = ?", (id_orden,)).fetchone()
        return row_to_dict(row)
