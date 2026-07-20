.PHONY: up down rebuild seed test logs clean
up:
	docker compose up --build -d
down:
	docker compose down
rebuild:
	docker compose build --no-cache
	docker compose up -d
seed:
	docker compose restart inventario-java
test:
	python -m pytest -q tests/contract services/ordenes-python/tests
	python tests/integration/e2e.py
	python tests/integration/idempotency.py
	python tests/integration/dlq.py
logs:
	docker compose logs -f
clean:
	docker compose down -v --remove-orphans
