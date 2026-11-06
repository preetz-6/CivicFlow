DC = docker compose
API = $(DC) exec api

.PHONY: up down logs migrate seed demo test record replay sim rain reset types

up:
	$(DC) up -d --build

down:
	$(DC) down

logs:
	$(DC) logs -f api

migrate:
	$(API) alembic upgrade head

seed:
	$(API) python -m app.seed.build

reset:
	$(API) python -m app.seed.build --reset

demo:
	$(API) python -m app.seed.build --reset --demo --paused

test:
	$(API) pytest
	cd web && npx playwright test

record:
	$(DC) exec -e AGENT_MODE=record api python -m app.seed.record_demo

sim:
	$(DC) run --rm simulator python sim.py --stream --rate 5

rain:
	$(DC) run --rm simulator python sim.py --scenario rain

types:
	cd web && npx openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.d.ts
