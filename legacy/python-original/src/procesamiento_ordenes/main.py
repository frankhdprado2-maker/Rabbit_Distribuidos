from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.procesamiento_ordenes import db
from src.procesamiento_ordenes.service import crear_orden
from src.shared.constants import SERVICE_ORDENES
from src.shared.logging_utils import configure_logging


logger = configure_logging(SERVICE_ORDENES)
app = FastAPI(title="FISI Tiendas Utiles - Procesamiento de Ordenes", version="0.7.0")


class OrdenItemIn(BaseModel):
    codigo_articulo: str
    cantidad: int = Field(gt=0)


class OrdenIn(BaseModel):
    cliente_id: str
    nombre_cliente: str
    ruc_cliente: str
    items: list[OrdenItemIn]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_ORDENES}


@app.get("/productos")
def productos() -> list[dict]:
    return db.listar_productos()


@app.post("/ordenes", status_code=201)
def registrar_orden(orden: OrdenIn) -> dict[str, str]:
    try:
        result = crear_orden(
            cliente_id=orden.cliente_id,
            nombre_cliente=orden.nombre_cliente,
            ruc_cliente=orden.ruc_cliente,
            items=orden.items,
        )
        logger.info(
            "Orden creada id_orden=%s correlation_id=%s estado=%s",
            result["id_orden"],
            result["correlation_id"],
            result["estado"],
        )
        return result
    except ValueError as exc:
        logger.warning("Validacion fallida al registrar orden: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/ordenes/{id_orden}")
def consultar_orden(id_orden: str) -> dict:
    orden = db.obtener_orden(id_orden)
    if orden is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada.")
    return orden


@app.get("/ordenes/{id_orden}/historial")
def historial_orden(id_orden: str) -> list[dict]:
    if db.obtener_orden(id_orden) is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada.")
    return db.obtener_historial(id_orden)
