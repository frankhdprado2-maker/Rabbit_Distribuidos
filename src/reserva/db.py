from src.shared.database import row_to_dict, get_connection


def obtener_reserva_por_orden(id_orden: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM reservas WHERE id_orden = ?", (id_orden,)).fetchone()
        return row_to_dict(row)
