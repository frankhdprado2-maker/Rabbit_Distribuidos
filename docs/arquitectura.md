# Arquitectura

## Flujo exitoso

```mermaid
sequenceDiagram
  participant C as Cliente
  participant P as Python Órdenes
  participant R as RabbitMQ
  participant J as Java Inventario
  participant T as TypeScript Reserva
  participant D as C# Facturación
  participant G as Go CxC
  C->>P: POST /ordenes
  P->>R: inventario.validar
  R->>J: ACK manual al finalizar
  J->>R: reserva.crear
  R->>T: reserva.crear
  T->>R: factura.generar
  R->>D: factura.generar
  D->>R: cuenta.crear
  R->>G: cuenta.crear
  G->>R: orden.confirmar
  R->>P: orden.confirmar
  P-->>C: GET = CONFIRMADA
```

## Rechazo

```mermaid
sequenceDiagram
  participant C as Cliente
  participant P as Python
  participant R as RabbitMQ
  participant J as Java Inventario
  C->>P: POST /ordenes
  P->>R: inventario.validar
  R->>J: entrega
  J->>J: producto/activo/stock
  J->>R: orden.error
  R->>P: orden.error
  P-->>C: GET = RECHAZADA + motivo
```

Cada dominio crea sus tablas al arrancar en su propia base. No hay foreign keys ni consultas entre bases. Inventario es el único dueño del stock. La traza de estados viaja en el payload y Python la materializa al recibir el evento terminal.
