PY=python3
VENV=.venv
PIP=$(VENV)/bin/pip
RUN=$(VENV)/bin/streamlit

.DEFAULT_GOAL := help

.PHONY: help setup lint format typecheck test run clean

help:
	@echo ""
	@echo "Bug Resolution Radar - comandos"
	@echo ""
	@echo "  make setup       Crea venv e instala dependencias (incluye dev)"
	@echo "  make run         Arranca la UI (Streamlit) en localhost"
	@echo "  make format      Formatea el código (black)"
	@echo "  make lint        Lint (ruff)"
	@echo "  make typecheck   Typecheck (mypy)"
	@echo "  make test        Tests (pytest)"
	@echo "  make clean       Borra venv y cachés"
	@echo ""
	@echo "Variables útiles:"
	@echo "  PY=python3       (puedes cambiarlo al invocar: make setup PY=python3.11)"
	@echo ""

setup:
	$(PY) -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"
	@echo "Done. Activate with: source .venv/bin/activate"

format:
	$(VENV)/bin/black .

lint:
	$(VENV)/bin/ruff check .

typecheck:
	$(VENV)/bin/mypy .

test:
	$(VENV)/bin/pytest -q

run:
	$(RUN) run app.py

clean:
	rm -rf $(VENV) .mypy_cache .pytest_cache .ruff_cache .coverage htmlcov
