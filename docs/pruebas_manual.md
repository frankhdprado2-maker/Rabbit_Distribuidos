# Pruebas manuales

Antes de probar:

```powershell
docker compose up -d
python scripts/init_db.py
python scripts/seed_data.py
uvicorn src.procesamiento_ordenes.main:app --reload --port 8080
python -m src.procesamiento_ordenes.response_consumer
python -m src.inventario.worker
python -m src.reserva.worker
python -m src.facturacion.worker
python -m src.cuentas_cobrar.worker
```

Abrir Swagger:

```text
http://localhost:8080/docs
```

Abrir RabbitMQ Management:

```text
http://localhost:15672
```

Usuario: `guest`

Contrasena: `guest`

## Prueba 1: Flujo exitoso

Enviar en `POST /ordenes`:

```json
{
  "cliente_id": "CLI-001",
  "nombre_cliente": "Juan Perez",
  "ruc_cliente": "10456789123",
  "items": [
    {
      "codigo_articulo": "ART-001",
      "cantidad": 2
    },
    {
      "codigo_articulo": "ART-002",
      "cantidad": 5
    }
  ]
}
```

Resultado esperado:

- La orden queda `CONFIRMADA`.
- Se crea reserva.
- Se crea factura.
- Se crea cuenta por cobrar.
- Se registra historial completo.
- En RabbitMQ Management se observa actividad en las colas.

Verificacion sugerida:

```powershell
curl http://localhost:8080/ordenes/ORD-2026-000001
curl http://localhost:8080/ordenes/ORD-2026-000001/historial
```

## Prueba 2: Rechazo por stock insuficiente

Enviar en `POST /ordenes`:

```json
{
  "cliente_id": "CLI-002",
  "nombre_cliente": "Maria Lopez",
  "ruc_cliente": "20456789123",
  "items": [
    {
      "codigo_articulo": "ART-005",
      "cantidad": 99
    }
  ]
}
```

Resultado esperado:

- La orden queda `RECHAZADA`.
- El motivo indica stock insuficiente.
- No se crea reserva.
- No se crea factura.
- No se crea cuenta por cobrar.
- Se registra historial con `orden.error`.

Verificacion sugerida:

```powershell
curl http://localhost:8080/ordenes/ORD-2026-000002
curl http://localhost:8080/ordenes/ORD-2026-000002/historial
```
