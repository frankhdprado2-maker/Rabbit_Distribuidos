# Evidencia ejecutada — 2026-07-20

- Build Docker: cinco imágenes compiladas.
- E2E: `ORD-2026-000004` CONFIRMADA, correlation `39993046-0de9-42c7-9aa5-0dc05695237b`, total 3835.00.
- Rechazo: `ORD-2026-000005` RECHAZADA sin reserva/factura/cuenta.
- Duplicado: `ORD-2026-000007`; stock 94 antes/después y conteos reserva/factura/cuenta `1/1/1` antes/después.
- Consumidor caído: `ORD-2026-000008` quedó en `cola_facturacion` con C# detenido y terminó CONFIRMADA al reiniciarlo.
- DLQ: message `37b5855f-6028-42ff-aeb3-e00b7728843c` llegó como `error.tecnico`, `attempt=4`.
- Unit/contract: pytest 3 passed, TypeScript 1 passed, Go 1 passed, .NET xUnit 1 passed; Maven package ejecutó el test Java.

Los primeros ensayos detectaron y corrigieron: permisos de `.erlang.cookie`, usuario omitido al importar definitions, JSR-310 no registrado, carrera RECHAZADA/VALIDANDO_STOCK y fuga de listeners de publisher confirms en Go.
