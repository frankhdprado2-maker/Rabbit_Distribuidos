from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from src.shared.database import get_connection


PRODUCTOS = [
    ("ART-001", "Cuaderno A4", 8.50, 50, 1),
    ("ART-002", "Lapicero azul", 1.50, 100, 1),
    ("ART-003", "Folder manila", 0.80, 80, 1),
    ("ART-004", "Plumon negro", 3.20, 20, 1),
    ("ART-005", "Resaltador", 4.00, 5, 1),
]


def main() -> None:
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO articulos (
                codigo_articulo, nombre_articulo, precio_unitario, cantidad_existente, activo
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(codigo_articulo) DO UPDATE SET
                nombre_articulo = excluded.nombre_articulo,
                precio_unitario = excluded.precio_unitario,
                cantidad_existente = excluded.cantidad_existente,
                activo = excluded.activo
            """,
            PRODUCTOS,
        )
        conn.commit()
    print("Datos de prueba cargados correctamente.")


if __name__ == "__main__":
    main()
