# Contrato de mensajes

El sobre canónico está en `contracts/event-envelope.schema.json`; los seis payloads están en archivos por routing key y el catálogo está en `asyncapi.yaml`. `message_id` cambia en cada salto; `correlation_id` e `id_orden` se conservan; `causation_id` apunta al `message_id` anterior. `attempt` inicia en cero y solo aumenta al republicar un fallo técnico. JSON se codifica en UTF-8 y `event_type` debe ser igual a la routing key.

`trace` contiene etapas ya completadas (`estado`, `evento`, `message_id`, `causation_id`, descripción). No autoriza lógica cruzada: solo permite materializar la vista histórica en Órdenes.
