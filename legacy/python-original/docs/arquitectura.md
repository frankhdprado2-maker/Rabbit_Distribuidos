# Arquitectura de la solucion RabbitMQ

## Objetivo

La solucion simula la cadena de valor Gestion de Ordenes de Compra para FISI Tiendas Utiles usando middleware orientado a mensajes. Los modulos de negocio no se llaman por HTTP entre si; se comunican mediante eventos publicados en RabbitMQ.

## Componentes

- Procesamiento de Ordenes: API FastAPI para registrar y consultar ordenes. Publica `inventario.validar` y consume respuestas finales.
- Inventario: valida existencia, estado activo y stock de articulos.
- Reserva: descuenta stock y crea una reserva idempotente por orden.
- Facturacion: crea o reutiliza una factura por orden.
- Cuentas por Cobrar: crea o reutiliza una cuenta por cobrar por factura y confirma la orden.
- RabbitMQ: broker central con exchange direct durable.
- SQLite: persistencia local para articulos, ordenes, detalle, reservas, facturas, cuentas, historial y mensajes procesados.

## Flujo principal

1. El operador registra una orden en `POST /ordenes`.
2. La API guarda la orden en estado `PENDIENTE`.
3. La API publica `inventario.validar` en `fisi.ordenes.exchange`.
4. Inventario valida stock y publica `reserva.crear` o `orden.error`.
5. Reserva descuenta stock una sola vez y publica `factura.generar`.
6. Facturacion genera factura una sola vez y publica `cuenta.crear`.
7. Cuentas por Cobrar crea la cuenta y publica `orden.confirmar`.
8. Procesamiento de Ordenes consume `cola_respuesta` y actualiza la orden a `CONFIRMADA`, `RECHAZADA` o `ERROR`.

## Topologia RabbitMQ

Exchange principal:

- Nombre: `fisi.ordenes.exchange`
- Tipo: `direct`
- Durable: `true`

Exchange de errores:

- Nombre: `fisi.ordenes.dlx`
- Tipo: `direct`
- Durable: `true`

| Routing key | Cola |
| --- | --- |
| `inventario.validar` | `cola_inventario` |
| `reserva.crear` | `cola_reserva` |
| `factura.generar` | `cola_facturacion` |
| `cuenta.crear` | `cola_cxc` |
| `orden.confirmar` | `cola_respuesta` |
| `orden.error` | `cola_respuesta` |
| `error.tecnico` | `cola_errores` |

## Contrato de mensaje

Todos los eventos usan la envoltura estandar:

```json
{
  "message_id": "uuid",
  "event_type": "inventario.validar",
  "event_version": 1,
  "correlation_id": "uuid",
  "causation_id": null,
  "id_orden": "ORD-2026-000001",
  "timestamp": "ISO-8601",
  "source": "procesamiento-ordenes",
  "attempt": 0,
  "payload": {}
}
```

Los mensajes se publican como `application/json` con `delivery_mode=2`. Los consumidores usan ACK manual y confirman despues de procesar y publicar el siguiente evento.
