PY=python3
VENV=.venv
PIP=$(VENV)/bin/pip
PYTHON=$(VENV)/bin/python
RUN=$(VENV)/bin/streamlit

.DEFAULT_GOAL := help

.PHONY: help setup format lint typecheck test run clean

help:
	@echo ""
	@echo "Bug Resolution Radar - comandos"
	@echo ""
	@echo "  make setup       Prepara/actualiza el entorno completo (venv + deps dev, incluye black)"
	@echo "  make run         Arranca la UI (Streamlit) en localhost"
	@echo "  make format      Formatea el código (black, si está instalado)"
	@echo "  make lint        Lint (ruff, si está instalado)"
	@echo "  make typecheck   Typecheck (mypy, si está instalado)"
	@echo "  make test        Tests (pytest, si está instalado)"
	@echo "  make clean       Borra venv y cachés"
	@echo ""
	@echo "Variables útiles:"
	@echo "  PY=python3       (puedes cambiarlo al invocar: make setup PY=python3.11)"
	@echo ""

setup:
	@if [ ! -d $(VENV) ]; then $(PY) -m venv $(VENV); fi
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"
	@echo ""
	@echo "Entorno listo."
	@echo "Activa con: source .venv/bin/activate"

format:
	@if [ -f $(VENV)/bin/black ]; then \
		$(VENV)/bin/black . ; \
	else \
		echo "black no está instalado en el venv."; \
	fi

lint:
	@if [ -f $(VENV)/bin/ruff ]; then \
		$(VENV)/bin/ruff check . ; \
	else \
		echo "ruff no está instalado en el venv."; \
	fi

typecheck:
	@if [ -f $(VENV)/bin/mypy ]; then \
		$(VENV)/bin/mypy src ; \
	else \
		echo "mypy no está instalado en el venv."; \
	fi

test:
	@if [ -f $(VENV)/bin/pytest ]; then \
		$(VENV)/bin/pytest -q ; \
	else \
		echo "pytest no está instalado en el venv."; \
	fi

run:
	$(RUN) run app.py

clean:
	rm -rf $(VENV) .mypy_cache .pytest_cache .ruff_cache .coverage htmlcov
