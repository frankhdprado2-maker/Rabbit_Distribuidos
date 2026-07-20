import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

import pika
import psycopg
from fastapi import FastAPI, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

SERVICE = "procesamiento-ordenes"
EXCHANGE = "fisi.ordenes.exchange"
DLX = "fisi.ordenes.dlx"
QUEUE = "cola_respuesta"
DB_URL = os.getenv("DATABASE_URL", "postgresql://ordenes_user:ordenes_dev@postgres:5432/db_ordenes")
RABBIT_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBIT_USER = os.getenv("RABBITMQ_USER", "fisi")
RABBIT_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "fisi_dev")
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
log = logging.getLogger(SERVICE)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def structured(level: str, action: str, result: str, event: dict[str, Any] | None = None, duration_ms: int = 0) -> None:
    event = event or {}
    getattr(log, level.lower())(json.dumps({
        "timestamp": now(), "level": level, "service": SERVICE, "language": "python",
        "event_type": event.get("event_type"), "message_id": event.get("message_id"),
        "correlation_id": event.get("correlation_id"), "causation_id": event.get("causation_id"),
        "id_orden": event.get("id_orden"), "attempt": event.get("attempt", 0),
        "action": action, "result": result, "duration_ms": duration_ms,
    }, ensure_ascii=False))


class ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    codigo_articulo: str = Field(min_length=1)
    cantidad: int = Field(gt=0)


class OrdenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cliente_id: str = Field(min_length=1)
    nombre_cliente: str = Field(min_length=1)
    ruc_cliente: str = Field(pattern=r"^\d{11}$")
    items: list[ItemIn] = Field(min_length=1)


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: UUID
    event_type: Literal["orden.confirmar", "orden.error", "error.tecnico"]
    event_version: Literal[1]
    correlation_id: UUID
    causation_id: UUID | None
    id_orden: str = Field(pattern=r"^ORD-\d{4}-\d{6}$")
    timestamp: datetime
    source: str
    attempt: int = Field(ge=0)
    payload: dict[str, Any]


def db():
    return psycopg.connect(DB_URL, row_factory=dict_row)


def initialize() -> None:
    deadline = time.time() + 90
    while True:
        try:
            with db() as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS orden_sequence(id BIGSERIAL PRIMARY KEY)""")
                conn.execute("""CREATE TABLE IF NOT EXISTS ordenes(
                    id_orden VARCHAR(32) PRIMARY KEY, cliente_id TEXT NOT NULL, nombre_cliente TEXT NOT NULL,
                    ruc_cliente TEXT NOT NULL, estado TEXT NOT NULL, total_preliminar NUMERIC(14,2) NOT NULL DEFAULT 0,
                    total_final NUMERIC(14,2), correlation_id UUID NOT NULL UNIQUE, reserva_id TEXT,
                    numero_factura TEXT, cuenta_cobrar_id TEXT, motivo_error TEXT,
                    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT NOW(), fecha_actualizacion TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
                conn.execute("""CREATE TABLE IF NOT EXISTS detalle_orden(
                    id BIGSERIAL PRIMARY KEY, id_orden VARCHAR(32) NOT NULL REFERENCES ordenes(id_orden),
                    codigo_articulo TEXT NOT NULL, cantidad INTEGER NOT NULL CHECK(cantidad > 0))""")
                conn.execute("""CREATE TABLE IF NOT EXISTS historial_orden(
                    id BIGSERIAL PRIMARY KEY, id_orden VARCHAR(32) NOT NULL REFERENCES ordenes(id_orden),
                    estado TEXT NOT NULL, evento TEXT NOT NULL, message_id UUID, correlation_id UUID NOT NULL,
                    causation_id UUID, descripcion TEXT NOT NULL, fecha TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
                conn.execute("""CREATE TABLE IF NOT EXISTS mensajes_procesados(
                    message_id UUID PRIMARY KEY, id_orden VARCHAR(32) NOT NULL, procesado_en TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            return
        except Exception:
            if time.time() >= deadline:
                raise
            time.sleep(2)


def rabbit_connection() -> pika.BlockingConnection:
    credentials = pika.PlainCredentials(RABBIT_USER, RABBIT_PASSWORD)
    return pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST, 5672, "/", credentials,
        heartbeat=30, blocked_connection_timeout=30, connection_attempts=5, retry_delay=2))


def publish(event: dict[str, Any]) -> None:
    with rabbit_connection() as connection:
        channel = connection.channel()
        channel.confirm_delivery()
        channel.basic_publish(EXCHANGE, event["event_type"], json.dumps(event, ensure_ascii=False).encode(),
            pika.BasicProperties(content_type="application/json", content_encoding="utf-8", delivery_mode=2,
                message_id=event["message_id"], correlation_id=event["correlation_id"]), mandatory=True)


def retry_or_dlq(channel, method, raw: dict[str, Any], reason: str) -> None:
    attempt = int(raw.get("attempt", 0)) + 1
    raw["attempt"] = attempt
    raw["timestamp"] = now()
    raw["source"] = SERVICE
    body = json.dumps(raw, ensure_ascii=False).encode()
    props = pika.BasicProperties(content_type="application/json", delivery_mode=2,
        message_id=str(raw.get("message_id", uuid4())), correlation_id=str(raw.get("correlation_id", "")),
        headers={"x-error": reason})
    if attempt > MAX_RETRIES:
        raw["event_type"] = "error.tecnico"
        channel.basic_publish(DLX, "error.tecnico", json.dumps(raw, ensure_ascii=False).encode(), props)
    else:
        time.sleep(int(os.getenv("RETRY_DELAY_MS", "5000")) / 1000)
        channel.basic_publish(EXCHANGE, method.routing_key, body, props)
    channel.basic_ack(method.delivery_tag)


def on_response(channel, method, properties, body: bytes) -> None:
    started = time.perf_counter()
    raw: dict[str, Any] = {}
    try:
        raw = json.loads(body.decode("utf-8"))
        event = Envelope.model_validate(raw)
        if event.event_type != method.routing_key:
            raise ValueError("event_type no coincide con routing key")
        with db() as conn:
            if conn.execute("SELECT 1 FROM mensajes_procesados WHERE message_id=%s", (event.message_id,)).fetchone():
                structured("INFO", "mensaje_ignorado_idempotencia", "duplicate", raw)
                channel.basic_ack(method.delivery_tag)
                return
            order = conn.execute("SELECT 1 FROM ordenes WHERE id_orden=%s FOR UPDATE", (event.id_orden,)).fetchone()
            if not order:
                raise ValueError("orden desconocida")
            trace = event.payload.get("trace", [])
            for stage in trace:
                conn.execute("""INSERT INTO historial_orden(id_orden,estado,evento,message_id,correlation_id,causation_id,descripcion)
                    VALUES(%s,%s,%s,%s,%s,%s,%s)""", (event.id_orden, stage["estado"], stage["evento"],
                    stage.get("message_id"), event.correlation_id, stage.get("causation_id"), stage.get("descripcion", stage["evento"])))
            if event.event_type == "orden.confirmar":
                p = event.payload
                conn.execute("""UPDATE ordenes SET estado='CONFIRMADA', total_preliminar=%s, total_final=%s, reserva_id=%s,
                    numero_factura=%s, cuenta_cobrar_id=%s, fecha_actualizacion=NOW() WHERE id_orden=%s""",
                    (p["subtotal"], p["total"], p["reserva_id"], p["numero_factura"], p["cuenta_cobrar_id"], event.id_orden))
                state, description = "CONFIRMADA", "Orden confirmada por Cuentas por Cobrar."
            else:
                state, description = "RECHAZADA", event.payload["message"]
                conn.execute("UPDATE ordenes SET estado=%s,motivo_error=%s,fecha_actualizacion=NOW() WHERE id_orden=%s",
                    (state, description, event.id_orden))
            conn.execute("""INSERT INTO historial_orden(id_orden,estado,evento,message_id,correlation_id,causation_id,descripcion)
                VALUES(%s,%s,%s,%s,%s,%s,%s)""", (event.id_orden, state, event.event_type, event.message_id,
                event.correlation_id, event.causation_id, description))
            conn.execute("INSERT INTO mensajes_procesados(message_id,id_orden) VALUES(%s,%s)", (event.message_id, event.id_orden))
        channel.basic_ack(method.delivery_tag)
        structured("INFO", "respuesta_aplicada", "success", raw, int((time.perf_counter()-started)*1000))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, KeyError) as exc:
        structured("ERROR", "mensaje_no_procesable", "dlq", raw)
        if raw:
            retry_or_dlq(channel, method, raw, str(exc))
        else:
            channel.basic_nack(method.delivery_tag, requeue=False)
    except Exception as exc:
        structured("ERROR", "fallo_tecnico", "retry", raw)
        retry_or_dlq(channel, method, raw, str(exc))


def consume_forever() -> None:
    delay = 1
    while True:
        try:
            connection = rabbit_connection()
            channel = connection.channel()
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(QUEUE, on_response, auto_ack=False)
            structured("INFO", "consumidor_iniciado", "success")
            channel.start_consuming()
        except Exception as exc:
            structured("ERROR", "conexion_consumidor", f"retry:{exc}")
            time.sleep(delay)
            delay = min(delay * 2, 30)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize()
    threading.Thread(target=consume_forever, daemon=True).start()
    yield


app = FastAPI(title="Procesamiento de Ordenes", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    try:
        with db() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "service": SERVICE, "language": "python"}
    except Exception as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/ordenes", status_code=202)
def create_order(order: OrdenIn):
    correlation_id, message_id = str(uuid4()), str(uuid4())
    with db() as conn:
        sequence = conn.execute("INSERT INTO orden_sequence DEFAULT VALUES RETURNING id").fetchone()["id"]
        id_orden = f"ORD-{datetime.now(timezone.utc).year}-{sequence:06d}"
        conn.execute("""INSERT INTO ordenes(id_orden,cliente_id,nombre_cliente,ruc_cliente,estado,correlation_id)
            VALUES(%s,%s,%s,%s,'PENDIENTE',%s)""", (id_orden, order.cliente_id, order.nombre_cliente, order.ruc_cliente, correlation_id))
        for item in order.items:
            conn.execute("INSERT INTO detalle_orden(id_orden,codigo_articulo,cantidad) VALUES(%s,%s,%s)",
                (id_orden, item.codigo_articulo, item.cantidad))
        conn.execute("""INSERT INTO historial_orden(id_orden,estado,evento,message_id,correlation_id,descripcion)
            VALUES(%s,'PENDIENTE','orden.registrada',%s,%s,'Orden registrada.')""", (id_orden, message_id, correlation_id))
        conn.execute("UPDATE ordenes SET estado='VALIDANDO_STOCK',fecha_actualizacion=NOW() WHERE id_orden=%s", (id_orden,))
        conn.execute("""INSERT INTO historial_orden(id_orden,estado,evento,message_id,correlation_id,descripcion)
            VALUES(%s,'VALIDANDO_STOCK','inventario.validar',%s,%s,'Evento preparado para publicacion persistente.')""", (id_orden, message_id, correlation_id))
    event = {"message_id": message_id, "event_type": "inventario.validar", "event_version": 1,
        "correlation_id": correlation_id, "causation_id": None, "id_orden": id_orden, "timestamp": now(),
        "source": SERVICE, "attempt": 0, "payload": {"cliente": {"cliente_id": order.cliente_id,
        "nombre_cliente": order.nombre_cliente, "ruc_cliente": order.ruc_cliente},
        "items": [i.model_dump() for i in order.items], "trace": []}}
    try:
        publish(event)
    except Exception as exc:
        structured("ERROR", "publicacion_inicial", "failed", event)
        with db() as conn:
            conn.execute("UPDATE ordenes SET estado='PENDIENTE',motivo_error=%s,fecha_actualizacion=NOW() WHERE id_orden=%s",
                ("RabbitMQ no disponible temporalmente.", id_orden))
        raise HTTPException(503, "Orden registrada; RabbitMQ no disponible temporalmente.") from exc
    structured("INFO", "orden_registrada", "success", event)
    return {"id_orden": id_orden, "estado": "PENDIENTE", "correlation_id": correlation_id,
        "mensaje": "Orden registrada y enviada para procesamiento."}


@app.get("/ordenes/{id_orden}")
def get_order(id_orden: str):
    with db() as conn:
        row = conn.execute("""SELECT id_orden,cliente_id,estado,total_preliminar,total_final,correlation_id,
            reserva_id,numero_factura,cuenta_cobrar_id,motivo_error,fecha_creacion,fecha_actualizacion
            FROM ordenes WHERE id_orden=%s""", (id_orden,)).fetchone()
    if not row:
        raise HTTPException(404, "Orden no encontrada")
    return row


@app.get("/ordenes/{id_orden}/historial")
def get_history(id_orden: str):
    with db() as conn:
        if not conn.execute("SELECT 1 FROM ordenes WHERE id_orden=%s", (id_orden,)).fetchone():
            raise HTTPException(404, "Orden no encontrada")
        return conn.execute("""SELECT estado,evento,message_id,correlation_id,causation_id,descripcion,fecha
            FROM historial_orden WHERE id_orden=%s ORDER BY id""", (id_orden,)).fetchall()
