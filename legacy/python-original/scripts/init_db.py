from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from src.shared.database import get_connection, get_db_path


SCHEMA = """
CREATE TABLE IF NOT EXISTS articulos (
    codigo_articulo TEXT PRIMARY KEY,
    nombre_articulo TEXT NOT NULL,
    precio_unitario REAL NOT NULL,
    cantidad_existente INTEGER NOT NULL,
    activo INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ordenes (
    id_orden TEXT PRIMARY KEY,
    cliente_id TEXT NOT NULL,
    nombre_cliente TEXT NOT NULL,
    ruc_cliente TEXT NOT NULL,
    estado TEXT NOT NULL,
    total_preliminar REAL NOT NULL,
    correlation_id TEXT NOT NULL,
    motivo_error TEXT,
    reserva_id TEXT,
    numero_factura TEXT,
    cuenta_id TEXT,
    fecha_creacion TEXT NOT NULL,
    fecha_actualizacion TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS detalle_orden (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_orden TEXT NOT NULL,
    codigo_articulo TEXT NOT NULL,
    nombre_articulo TEXT NOT NULL,
    cantidad INTEGER NOT NULL,
    precio_unitario REAL NOT NULL,
    subtotal REAL NOT NULL,
    FOREIGN KEY (id_orden) REFERENCES ordenes(id_orden)
);

CREATE TABLE IF NOT EXISTS reservas (
    id_reserva TEXT PRIMARY KEY,
    id_orden TEXT UNIQUE NOT NULL,
    estado_reserva TEXT NOT NULL,
    fecha_reserva TEXT NOT NULL,
    FOREIGN KEY (id_orden) REFERENCES ordenes(id_orden)
);

CREATE TABLE IF NOT EXISTS facturas (
    numero_factura TEXT PRIMARY KEY,
    id_orden TEXT UNIQUE NOT NULL,
    cliente_id TEXT NOT NULL,
    nombre_cliente TEXT NOT NULL,
    ruc_cliente TEXT NOT NULL,
    subtotal REAL NOT NULL,
    total_igv REAL NOT NULL,
    total_factura REAL NOT NULL,
    fecha_emision TEXT NOT NULL,
    FOREIGN KEY (id_orden) REFERENCES ordenes(id_orden)
);

CREATE TABLE IF NOT EXISTS cuentas_cobrar (
    id_cuenta TEXT PRIMARY KEY,
    numero_factura TEXT UNIQUE NOT NULL,
    cliente_id TEXT NOT NULL,
    nombre_cliente TEXT NOT NULL,
    ruc_cliente TEXT NOT NULL,
    total_cobrar REAL NOT NULL,
    fecha_cobro TEXT NOT NULL,
    estado_registro TEXT NOT NULL,
    FOREIGN KEY (numero_factura) REFERENCES facturas(numero_factura)
);

CREATE TABLE IF NOT EXISTS historial_orden (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_orden TEXT NOT NULL,
    estado TEXT NOT NULL,
    evento TEXT NOT NULL,
    routing_key TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    message_id TEXT,
    descripcion TEXT NOT NULL,
    fecha TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mensajes_procesados (
    message_id TEXT PRIMARY KEY,
    id_orden TEXT NOT NULL,
    servicio TEXT NOT NULL,
    fecha TEXT NOT NULL
);
"""


def main() -> None:
    db_path = get_db_path()
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.commit()
    print(f"Base de datos inicializada en {db_path}")


if __name__ == "__main__":
    main()
