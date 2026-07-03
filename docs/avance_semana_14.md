# Avance tecnico semana 14

## Alcance implementado al 70%

Se implemento una aplicacion funcional orientada a eventos para demostrar la gestion de ordenes de compra con RabbitMQ como bus central. La solucion cubre los casos de uso CU-01 al CU-10 y deja CU-11 cubierto por scripts de base de datos y CU-12 parcialmente cubierto con cola de errores.

## Modulos completados

- Procesamiento de Ordenes con FastAPI.
- Administracion de Inventario como consumidor RabbitMQ.
- Reserva como consumidor RabbitMQ e idempotencia por orden.
- Facturacion como consumidor RabbitMQ e idempotencia por orden.
- Cuentas por Cobrar como consumidor RabbitMQ e idempotencia por factura.

## Persistencia

SQLite mantiene:

- Catalogo de articulos.
- Ordenes y detalle.
- Reservas.
- Facturas.
- Cuentas por cobrar.
- Historial de trazabilidad.
- Mensajes procesados para idempotencia.

## Comunicacion asincrona

El flujo principal se ejecuta mediante routing keys y colas durables. No existen llamadas HTTP internas entre los modulos de negocio.

## Pendiente para el 100%

- Panel de supervision de errores y reprocesamiento.
- Pruebas automatizadas de integracion.
- Separacion fisica de bases de datos por modulo.
- Observabilidad mas completa con metricas.
- Configuracion avanzada de reintentos y backoff.
