# Manejo de errores

Negocio: producto inexistente/inactivo o stock insuficiente genera `orden.error` sin reintento. Técnico: conexión/SQL/excepción/contrato no procesable se republica con demora y `attempt+1`; superado `MAX_RETRIES` se publica en `fisi.ordenes.dlx` con `error.tecnico`. Los consumidores usan ACK manual y solo confirman tras transacción/publicación exitosa.

La compensación `reserva.liberar` se emite cuando Facturación agota reintentos. Java registra un movimiento `LIBERACION` único por orden/artículo y repone stock solo si existía `RESERVA`.
