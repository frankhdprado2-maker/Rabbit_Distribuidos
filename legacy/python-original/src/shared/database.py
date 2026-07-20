import sqlite3
from pathlib import Path
from typing import Any

from src.shared.config import get_settings
from src.shared.message_contracts import utc_now_iso


def get_db_path() -> Path:
    path = get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def fetch_all_dicts(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def already_processed(conn: sqlite3.Connection, message_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM mensajes_procesados WHERE message_id = ?",
        (message_id,),
    ).fetchone()
    return row is not None


def mark_processed(conn: sqlite3.Connection, *, message_id: str, id_orden: str, servicio: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO mensajes_procesados (message_id, id_orden, servicio, fecha)
        VALUES (?, ?, ?, ?)
        """,
        (message_id, id_orden, servicio, utc_now_iso()),
    )


def add_history(
    conn: sqlite3.Connection,
    *,
    id_orden: str,
    estado: str,
    evento: str,
    routing_key: str,
    correlation_id: str,
    message_id: str | None,
    descripcion: str,
) -> None:
    conn.execute(
        """
        INSERT INTO historial_orden (
            id_orden, estado, evento, routing_key, correlation_id, message_id, descripcion, fecha
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            id_orden,
            estado,
            evento,
            routing_key,
            correlation_id,
            message_id,
            descripcion,
            utc_now_iso(),
        ),
    )


def update_order_status(
    conn: sqlite3.Connection,
    *,
    id_orden: str,
    estado: str,
    motivo_error: str | None = None,
    reserva_id: str | None = None,
    numero_factura: str | None = None,
    cuenta_id: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE ordenes
        SET estado = ?,
            motivo_error = COALESCE(?, motivo_error),
            reserva_id = COALESCE(?, reserva_id),
            numero_factura = COALESCE(?, numero_factura),
            cuenta_id = COALESCE(?, cuenta_id),
            fecha_actualizacion = ?
        WHERE id_orden = ?
        """,
        (
            estado,
            motivo_error,
            reserva_id,
            numero_factura,
            cuenta_id,
            utc_now_iso(),
            id_orden,
        ),
    )
