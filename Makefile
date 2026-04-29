PYTHON := .venv/bin/python
BACKEND_STAMP := .venv/.backend-installed

PIP_FLAGS ?=

.PHONY: venv setup dev test eval docker deploy-cloud-run-docs backend-install frontend-install backend-dev frontend-dev

.venv/bin/python:
	python3 -m venv .venv

venv: .venv/bin/python

setup: backend-install frontend-install

$(BACKEND_STAMP): .venv/bin/python backend/pyproject.toml
	$(PYTHON) -m pip install $(PIP_FLAGS) setuptools wheel
	$(PYTHON) -m pip install $(PIP_FLAGS) --no-build-isolation -e 'backend[dev]' || \
	$(PYTHON) -m pip install $(PIP_FLAGS) --ignore-installed --no-deps --no-build-isolation -e 'backend[dev]'
	@touch $(BACKEND_STAMP)

backend-install: $(BACKEND_STAMP)

frontend-install:
	npm --prefix frontend install

dev:
	docker compose up --build

test: backend-install frontend-install
	$(PYTHON) -m ruff check --config backend/pyproject.toml backend
	$(PYTHON) -m mypy --config-file backend/pyproject.toml backend/repolens
	PYTHONPATH=backend $(PYTHON) -m pytest backend/tests
	npm --prefix frontend run lint
	npm --prefix frontend run typecheck
	npm --prefix frontend run build

eval: backend-install
	PYTHONPATH=backend EMBEDDING_PROVIDER=hashing VECTOR_STORE_PROVIDER=memory ANSWER_PROVIDER=extractive $(PYTHON) scripts/run_sample_eval.py

backend-dev: backend-install
	PYTHONPATH=backend $(PYTHON) -m uvicorn repolens.main:app --host 0.0.0.0 --port 8000 --reload

frontend-dev: frontend-install
	npm --prefix frontend run dev -- --host 0.0.0.0 --port 5173

docker:
	docker compose build

deploy-cloud-run-docs:
	sed -n '1,240p' docs/deploy-cloud-run.md
