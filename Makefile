.PHONY: venv lint format test build deploy seed create-user frontend evaluate clean

ENV ?= dev
VENV := .venv
PY := $(VENV)/bin/python

venv:
	python3.12 -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements-dev.txt

lint:
	$(VENV)/bin/ruff check backend tests
	$(VENV)/bin/black --check backend tests

format:
	$(VENV)/bin/ruff check --fix backend tests
	$(VENV)/bin/black backend tests

test:
	RS_DATA_DIR=backend/data $(VENV)/bin/pytest tests/unit tests/component --cov

build:
	sam build --use-container

deploy:
	sam deploy --config-env $(ENV)

seed:
	./scripts/seed-config.sh $(ENV)

create-user:
	./scripts/create-user.sh $(ENV) $(EMAIL) $(GROUP)

frontend:
	./scripts/gen-frontend-env.sh $(ENV)
	./scripts/deploy-frontend.sh $(ENV)

evaluate:
	$(PY) scripts/evaluate.py --env $(ENV)

clean:
	rm -rf .aws-sam $(VENV) .pytest_cache .ruff_cache .coverage htmlcov
