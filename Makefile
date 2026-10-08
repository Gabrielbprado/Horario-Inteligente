.DEFAULT_GOAL := ajuda
SHELL := /bin/bash

ajuda:  ## Lista os alvos disponiveis
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

instalar:  ## Instala as dependencias de backend e frontend
	cd backend && uv sync
	cd frontend && npm install

migrar:  ## Aplica as migrations no banco configurado
	cd backend && uv run alembic upgrade head

seed:  ## Recria o banco com os dados de exemplo
	cd backend && uv run python -m scripts.seed

massa:  ## Enche o banco com uma regiao inteira (16 unidades)
	cd backend && uv run python -m scripts.massa --escala grande

massa-grades:  ## Idem, e roda o solver em cada unidade (demorado)
	cd backend && uv run python -m scripts.massa --escala grande --gerar-grades

massa-conflitos:  ## Massa grande com conflitos plantados de proposito, grades geradas e Fatecs publicadas
	cd backend && uv run python -m scripts.massa --escala grande --conflitos --gerar-grades

api:  ## Sobe a API em modo desenvolvimento
	cd backend && uv run uvicorn app.main:app --reload --port 8000

web:  ## Sobe o frontend em modo desenvolvimento
	cd frontend && npm run dev

teste:  ## Roda os testes de backend e frontend
	cd backend && uv run pytest -q
	cd frontend && npm run test

lint:  ## Roda os linters e o typecheck
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint && npm run typecheck

up:  ## Sobe tudo via docker compose
	docker compose up --build

down:  ## Derruba os containers
	docker compose down

.PHONY: ajuda instalar migrar seed massa massa-grades massa-conflitos api web teste lint up down
