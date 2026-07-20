# Pruebas manuales

Arranque con `docker compose up --build -d` y espere que `docker compose ps` muestre healthy. Ejecute `python tests/integration/e2e.py` para éxito/rechazo, `python tests/integration/idempotency.py` para replay y `powershell -ExecutionPolicy Bypass -File tests/integration/resilience.ps1` para comprobar persistencia con C# detenido. `python tests/integration/dlq.py` provoca un payload inválido controlado y exige `attempt=4` en `cola_errores`.

Estado de colas: `docker compose exec rabbitmq rabbitmqctl list_queues name messages consumers`. Estado de tablas: `docker compose exec postgres psql -U reserva_user -d db_reserva -c "TABLE reservas"`. Sustituya usuario/base para cada dominio.
