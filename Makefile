.PHONY: up down build logs ingest shell-api shell-ingestor shell-frontend

up:
	docker compose up

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

ingest:
	docker compose run --rm ingestor python main.py

shell-api:
	docker compose exec api bash

shell-ingestor:
	docker compose exec ingestor bash

shell-frontend:
	docker compose exec frontend sh
