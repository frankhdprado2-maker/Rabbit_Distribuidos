from src.shared.database import row_to_dict, get_connection


def obtener_cuenta_por_factura(numero_factura: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM cuentas_cobrar WHERE numero_factura = ?", (numero_factura,)).fetchone()
        return row_to_dict(row)
