# Reporte de pruebas - Avance 70%

## 1. Resultado general

El proyecto funciona correctamente como avance al 70%. Se valido el flujo distribuido:

```text
FastAPI -> RabbitMQ -> Inventario -> Reserva -> Facturacion -> Cuentas por Cobrar -> RabbitMQ -> Procesamiento de Ordenes
```

Los modulos de negocio no usan llamadas HTTP internas. La comunicacion se realiza mediante RabbitMQ, colas durables y routing keys.

Nota de ejecucion QA: el puerto `8080` estaba ocupado por una API ya abierta, por eso las pruebas automatizadas se ejecutaron en `http://127.0.0.1:18080` sin cerrar procesos del usuario. Para aislar las pruebas de consumidores ya existentes, se uso el vhost RabbitMQ `qa_fisi` con los mismos nombres de exchanges, colas y routing keys.

## 2. Inspeccion inicial

| Punto revisado | Resultado |
| --- | --- |
| Estructura real | Existen `src/`, `scripts/`, `docs/`, `data/`, `docker-compose.yml`, `requirements.txt`, `.env.example` y `README.md`. |
| Archivos principales | `src/procesamiento_ordenes/main.py`, `service.py`, `response_consumer.py`, workers de `inventario`, `reserva`, `facturacion`, `cuentas_cobrar`, y utilidades en `src/shared`. |
| Tecnologias detectadas | FastAPI, Uvicorn, Pika, python-dotenv, Pydantic, SQLite por libreria estandar, RabbitMQ por Docker Compose. |
| docker-compose.yml | Existe y usa `rabbitmq:3-management` con puertos `5672` y `15672`. |
| Scripts de base de datos | Existen `scripts/init_db.py` y `scripts/seed_data.py`. |
| Worker inventario | Existe `src/inventario/worker.py`. |
| Worker reserva | Existe `src/reserva/worker.py`. |
| Worker facturacion | Existe `src/facturacion/worker.py`. |
| Worker cuentas_cobrar | Existe `src/cuentas_cobrar/worker.py`. |
| response_consumer | Existe `src/procesamiento_ordenes/response_consumer.py`. |

## 3. Pruebas ejecutadas

| Codigo | Descripcion | Resultado esperado | Resultado obtenido | Estado |
| --- | --- | --- | --- | --- |
| P0 | Preparacion del entorno | Crear `.venv`, instalar dependencias, levantar RabbitMQ, inicializar DB y cargar datos | `.venv` creado, `pip install -r requirements.txt` OK, RabbitMQ en Docker OK, DB QA inicializada y seed cargado | APROBADO |
| P1 | Flujo exitoso | Orden `ORD-2026-000001` termina `CONFIRMADA`; crea detalle, reserva, factura, cuenta e historial | Orden `ORD-2026-000001` termino `CONFIRMADA`; detalle=2, reservas=1, facturas=1, cuentas=1, historial=7; stock `ART-001` de 50 a 48 y `ART-002` de 100 a 95 | APROBADO |
| P2 | Rechazo por stock insuficiente | Orden termina `RECHAZADA`; no crea reserva, factura ni cuenta; registra motivo | Orden `ORD-2026-000002` termino `RECHAZADA`; reservas=0, facturas=0, cuentas=0; motivo: `No existe stock suficiente para completar la orden.` | APROBADO |
| P3 | Validaciones de entrada | Orden sin items y cantidad cero deben rechazarse sin crear orden | Sin items devolvio HTTP 400; cantidad cero devolvio HTTP 422; conteo de ordenes no aumento | APROBADO |
| P4 | Idempotencia | Mensaje duplicado no debe duplicar stock, reserva, factura ni cuenta | Reprocesamiento controlado no modifico stock ni conteos; `mensajes_procesados` registra 7 mensajes; no hubo publicaciones extra | APROBADO |
| P5 | Historial y trazabilidad | `correlation_id` se conserva y `historial_orden` tiene campos completos | `correlation_id` unico durante el flujo exitoso; historial con `estado`, `evento`, `routing_key`, `correlation_id`, `message_id`, `descripcion`, `fecha` | APROBADO |
| P6 | ACK manual | No usar `auto_ack=True`; usar ACK despues de procesar y NACK ante error | Todos los consumers usan `auto_ack=False`, `basic_ack` al final del callback y `basic_nack(..., requeue=False)` ante excepcion | APROBADO |
| P7 | RabbitMQ Management | Exchanges, colas, bindings y consumers disponibles; sin mensajes acumulados | Exchanges `fisi.ordenes.exchange` y `fisi.ordenes.dlx` durables; colas principales con consumers; mensajes acumulados=0 | APROBADO |
| P8 | README | Instrucciones claras de instalacion, ejecucion y pruebas | README incluye dependencias, RabbitMQ, DB, API, workers, Swagger, Management y pruebas manuales | APROBADO |

## 4. Errores encontrados

No se encontraron errores de codigo durante la prueba.

Observaciones operativas:

- El puerto `8080` estaba ocupado al iniciar la QA. Se uso `18080` para no cerrar la API del usuario.
- Habia consumidores conectados en el vhost RabbitMQ por defecto. Se uso el vhost aislado `qa_fisi` para evitar que las pruebas se mezclen con terminales abiertas.
- PowerShell mostro resultados vacios al consultar RabbitMQ con `Invoke-RestMethod`; se valido correctamente con `curl.exe` contra la API de RabbitMQ Management.

## 5. Correcciones aplicadas

No se aplicaron correcciones de codigo porque todas las pruebas pasaron.

Cambios no funcionales realizados para QA:

- Se creo el entorno virtual `.venv`.
- Se creo la base de prueba `data/qa_fisi_ordenes.db`.
- Se creo el vhost RabbitMQ `qa_fisi`.
- Se genero este reporte en `docs/reporte_pruebas_semana14.md`.

## 6. Evidencias para exposicion

Capturas recomendadas:

- Swagger con `POST /ordenes` exitoso.
- Swagger con `GET /ordenes/ORD-2026-000001`.
- Swagger con `GET /ordenes/ORD-2026-000001/historial`.
- RabbitMQ Management con exchanges `fisi.ordenes.exchange` y `fisi.ordenes.dlx`.
- RabbitMQ Management con colas `cola_inventario`, `cola_reserva`, `cola_facturacion`, `cola_cxc`, `cola_respuesta`, `cola_errores`.
- RabbitMQ Management mostrando consumers conectados y mensajes acumulados en cero.
- Base de datos con orden `ORD-2026-000001` en estado `CONFIRMADA`.
- Base de datos con factura `F001-000001`.
- Base de datos con cuenta por cobrar en estado `PENDIENTE`.
- Base de datos con orden `ORD-2026-000002` en estado `RECHAZADA` por stock insuficiente.

## 7. Evidencia de datos finales

Orden exitosa:

```text
id_orden: ORD-2026-000001
estado: CONFIRMADA
numero_factura: F001-000001
total_factura: 28.91
cuenta_id: CXC-E0FAD9FF05
```

Orden rechazada:

```text
id_orden: ORD-2026-000002
estado: RECHAZADA
motivo_error: No existe stock suficiente para completar la orden.
```

RabbitMQ QA:

```text
cola_inventario: consumers=1, messages=0
cola_reserva: consumers=1, messages=0
cola_facturacion: consumers=1, messages=0
cola_cxc: consumers=1, messages=0
cola_respuesta: consumers=1, messages=0
cola_errores: consumers=0, messages=0
```

Bindings validados:

```text
inventario.validar -> cola_inventario
reserva.crear -> cola_reserva
factura.generar -> cola_facturacion
cuenta.crear -> cola_cxc
orden.confirmar -> cola_respuesta
orden.error -> cola_respuesta
error.tecnico -> cola_errores
```

## 8. Conclusion

El proyecto esta listo para presentarse como avance 70%. Cumple con la arquitectura orientada a eventos, usa RabbitMQ como broker central, mantiene trazabilidad por `correlation_id`, persiste datos en SQLite, valida casos exitosos y de rechazo, y demuestra idempotencia en los modulos criticos.
