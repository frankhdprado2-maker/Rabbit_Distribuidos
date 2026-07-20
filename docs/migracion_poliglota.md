# Migración poliglota y rollback

La línea base era cinco workers Python sobre una SQLite compartida. Se conservó Órdenes en FastAPI y se reescribieron Inventario (Java), Reserva (TypeScript), Facturación (C#) y CxC (Go). SQLite compartida fue sustituida por cinco bases PostgreSQL, y los DTO Python compartidos por representaciones locales del mismo contrato JSON.

Respaldo: rama `backup-python-original` y carpeta `legacy/python-original`. Para ejecutar el original, cree un worktree desde esa rama, instale `requirements.txt`, inicie su Compose y siga su README. Detenga primero este stack para liberar 5672/15672.
