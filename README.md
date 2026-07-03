# FISI Tiendas Utiles - Gestion de Ordenes con RabbitMQ

Aplicacion de laboratorio al 70% para simular la cadena de valor Gestion de Ordenes de Compra usando FastAPI, RabbitMQ, Pika y SQLite. RabbitMQ actua como bus de mensajes entre cinco modulos independientes, sin llamadas HTTP internas entre los modulos de negocio.

## Arquitectura

Flujo principal:

```text
Cliente / Operador
-> API Procesamiento de Ordenes
-> RabbitMQ
-> Inventario
-> Reserva
-> Facturacion
-> Cuentas por Cobrar
-> RabbitMQ
-> Procesamiento de Ordenes recibe confirmacion final
```

## Modulos implementados

- Procesamiento de Ordenes: API FastAPI, registro y consulta de ordenes, consumidor de respuesta final.
- Inventario: valida articulos, actividad y stock.
- Reserva: descuenta stock y evita reservas duplicadas.
- Facturacion: genera factura `F001-000001` y evita facturas duplicadas.
- Cuentas por Cobrar: crea cuenta pendiente con fecha de cobro a 30 dias y evita duplicados.

## Tecnologias usadas

- Python 3.11
- FastAPI
- Pika
- SQLite
- RabbitMQ
- Docker Compose
- python-dotenv
- Pydantic

## Flujo de eventos

1. `POST /ordenes` registra la orden y publica `inventario.validar`.
2. Inventario publica `reserva.crear` si hay stock o `orden.error` si hay rechazo de negocio.
3. Reserva descuenta stock y publica `factura.generar`.
4. Facturacion genera factura y publica `cuenta.crear`.
5. Cuentas por Cobrar genera cuenta y publica `orden.confirmar`.
6. Procesamiento de Ordenes consume `orden.confirmar` u `orden.error` desde `cola_respuesta`.

## Colas y routing keys

| Routing key | Cola | Proposito |
| --- | --- | --- |
| `inventario.validar` | `cola_inventario` | Validar productos y stock |
| `reserva.crear` | `cola_reserva` | Reservar productos |
| `factura.generar` | `cola_facturacion` | Generar factura |
| `cuenta.crear` | `cola_cxc` | Crear cuenta por cobrar |
| `orden.confirmar` | `cola_respuesta` | Confirmar orden |
| `orden.error` | `cola_respuesta` | Rechazar o marcar error |
| `error.tecnico` | `cola_errores` | Recibir mensajes enviados al DLX |

Exchange principal: `fisi.ordenes.exchange` tipo `direct`, durable.

Exchange de errores: `fisi.ordenes.dlx` tipo `direct`, durable.

## Instalacion

Crear entorno virtual:

```powershell
python -m venv .venv
```

Activacion en Windows:

```powershell
.venv\Scripts\activate
```

Instalar dependencias:

```powershell
pip install -r requirements.txt
```

Opcional: crear `.env` desde `.env.example` si deseas cambiar rutas o credenciales.

## Ejecucion

Levantar RabbitMQ:

```powershell
docker compose up -d
```

Inicializar base de datos:

```powershell
python scripts/init_db.py
```

Cargar datos:

```powershell
python scripts/seed_data.py
```

Ejecutar API:

```powershell
uvicorn src.procesamiento_ordenes.main:app --reload --port 8080
```

Ejecutar consumidores en terminales separadas:

```powershell
python -m src.procesamiento_ordenes.response_consumer
```

```powershell
python -m src.inventario.worker
```

```powershell
python -m src.reserva.worker
```

```powershell
python -m src.facturacion.worker
```

```powershell
python -m src.cuentas_cobrar.worker
```

Abrir Swagger:

[http://localhost:8080/docs](http://localhost:8080/docs)

Abrir RabbitMQ Management:

[http://localhost:15672](http://localhost:15672)

Usuario: `guest`

Contrasena: `guest`

## Pruebas manuales

Las pruebas completas estan en [docs/pruebas_manual.md](docs/pruebas_manual.md).

Casos cubiertos:

- Flujo exitoso hasta orden `CONFIRMADA`.
- Rechazo por stock insuficiente hasta orden `RECHAZADA`.

## Estados de orden

- `PENDIENTE`
- `VALIDANDO_STOCK`
- `RESERVADA`
- `FACTURADA`
- `CUENTA_CREADA`
- `CONFIRMADA`
- `RECHAZADA`
- `ERROR`

## Pendientes para completar el 100%

- Reprocesamiento supervisado desde una interfaz o endpoint administrativo.
- Reintentos con backoff y limites por tipo de error.
- Pruebas automatizadas de integracion con RabbitMQ.
- Separacion de bases por modulo para una distribucion mas realista.
- Metricas y trazas centralizadas.
