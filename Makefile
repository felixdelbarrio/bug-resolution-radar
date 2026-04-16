SHELL := /bin/bash

PY ?= python3
VENV ?= .venv
PIP = $(VENV)/bin/pip
PYTHON = $(VENV)/bin/python
PYTEST = $(VENV)/bin/pytest
PYINSTALLER = $(VENV)/bin/pyinstaller
NPM ?= npm
FRONTEND_DIR := frontend
FRONTEND_DIST := $(FRONTEND_DIR)/dist
API_HOST ?= 127.0.0.1
API_PORT ?= 8000
HOST_UNAME := $(shell uname -s 2>/dev/null || echo unknown)
ICON_SOURCE := assets/app_icon/source/BugResolutionRadarIcon.png
ICON_PNG := assets/app_icon/bug-resolution-radar.png
ICON_ICO := assets/app_icon/bug-resolution-radar.ico
ICON_ICNS := assets/app_icon/bug-resolution-radar.icns
ICON_PNG_ABS := $(PWD)/$(ICON_PNG)
ICON_ICNS_ABS := $(PWD)/$(ICON_ICNS)
PYINSTALLER_COLLECT_ARGS = \
	--paths "$(PWD)/src" \
	--collect-all bug_resolution_radar.analytics \
	--collect-all bug_resolution_radar.api \
	--collect-all bug_resolution_radar.common \
	--collect-all bug_resolution_radar.ingest \
	--collect-all bug_resolution_radar.models \
	--collect-all bug_resolution_radar.repositories \
	--collect-all bug_resolution_radar.reports \
	--collect-all bug_resolution_radar.services \
	--collect-all bug_resolution_radar.theme \
	--collect-all fastapi \
	--collect-all starlette \
	--collect-all uvicorn \
	--collect-all plotly \
	--collect-all browser_cookie3 \
	--collect-all openpyxl \
	--collect-all xlsxwriter \
	--collect-all pptx

.DEFAULT_GOAL := help

.PHONY: help setup test run run-api ci CI ci-format ci-typecheck ci-coverage ci-quality kill clean build build-frontend _ensure-backend _ensure-frontend _ensure-build _ensure-icon-assets _build-macos _build-linux

help:
	@echo ""
	@echo "Bug Resolution Radar"
	@echo ""
	@echo "  make setup        Instala backend + frontend"
	@echo "  make run          Compila frontend y abre la app desktop autocontenida"
	@echo "  make run-api      Compila frontend y sirve la SPA + API en http://127.0.0.1:8000"
	@echo "  make CI           Replica local de checks GitHub (format/typecheck/coverage/quality)"
	@echo "  make test         Ejecuta la suite Python seleccionada"
	@echo "  make build        Compila frontend y empaqueta desktop"
	@echo "  make kill         Detiene puertos 8000 y 5173"
	@echo "  make clean        Limpia venv, cachés y build frontend"
	@echo ""

setup:
	@if [ ! -d $(VENV) ]; then $(PY) -m venv $(VENV); fi
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"
	$(NPM) --prefix $(FRONTEND_DIR) install

_ensure-backend:
	@if [ ! -x "$(PYTHON)" ]; then echo "Ejecuta primero: make setup"; exit 1; fi

_ensure-frontend: _ensure-backend
	@if [ ! -d "$(FRONTEND_DIR)/node_modules" ]; then echo "Faltan dependencias frontend. Ejecuta: make setup"; exit 1; fi

_ensure-build: _ensure-backend
	@if [ ! -x "$(PYINSTALLER)" ]; then echo "Falta pyinstaller. Ejecuta: make setup"; exit 1; fi
	@if [ ! -d "$(FRONTEND_DIR)/node_modules" ]; then echo "Faltan dependencias frontend. Ejecuta: make setup"; exit 1; fi

_ensure-icon-assets: _ensure-backend
	@if [ ! -f "$(ICON_PNG)" ] || [ ! -f "$(ICON_ICO)" ] || [ ! -f "$(ICON_ICNS)" ]; then \
		if [ ! -f "$(ICON_SOURCE)" ]; then echo "Falta icono fuente: $(ICON_SOURCE)"; exit 1; fi; \
		PYTHONPATH=src $(PYTHON) scripts/update_app_icon.py --input "$(ICON_SOURCE)" --png-out "$(ICON_PNG)" --ico-out "$(ICON_ICO)" --icns-out "$(ICON_ICNS)"; \
	fi

test: _ensure-backend
	PYTHONPATH=src $(PYTEST) -q \
		tests/test_api_app.py \
		tests/test_run_desktop_entrypoint.py \
		tests/test_architecture_boundaries.py \
		tests/test_executive_report_ppt.py \
		tests/test_period_followup_report_ppt.py \
		tests/test_learning_store.py \
		tests/test_source_maintenance.py \
		tests/test_workspace_scope_sources.py \
		tests/test_browser_runtime_permissions.py \
		tests/test_security.py

run: _ensure-frontend _ensure-icon-assets build-frontend
	PYTHONPATH=src $(PYTHON) run_desktop.py

run-api: _ensure-frontend build-frontend
	PYTHONPATH=src $(PYTHON) run_api.py --host $(API_HOST) --port $(API_PORT)

ci: ci-format ci-typecheck ci-coverage ci-quality

CI: ci

ci-format: _ensure-backend
	PYTHONPATH=src $(PYTHON) -m ruff format --check .

ci-typecheck: _ensure-backend
	PYTHONPATH=src $(PYTHON) -m mypy src

ci-coverage: _ensure-backend
	PYTHONPATH=src $(PYTEST) -q --cov=bug_resolution_radar --cov-report=term-missing --cov-report=xml

ci-quality: _ensure-frontend
	$(PYTHON) -m pip check
	$(NPM) --prefix $(FRONTEND_DIR) run build
	PYTHONPATH=src $(PYTHON) scripts/check_docs_references.py
	PYTHONPATH=src $(PYTHON) scripts/check_dead_private_helpers.py
	PYTHONPATH=src $(PYTEST) -q tests/test_run_desktop_entrypoint.py
	PYTHONPATH=src $(PYTEST) -q tests/test_api_app.py
	PYTHONPATH=src $(PYTEST) -q tests/test_executive_report_ppt.py -k "kaleido_png_bytes_uses_cache or prerender_section_images_populates_payload"

build-frontend: _ensure-frontend
	$(NPM) --prefix $(FRONTEND_DIR) run build

build: _ensure-build _ensure-icon-assets build-frontend test
	@case "$(HOST_UNAME)" in \
		Darwin) $(MAKE) _build-macos ;; \
		Linux) $(MAKE) _build-linux ;; \
		*) echo "OS no soportado para make build: $(HOST_UNAME)"; exit 1 ;; \
	esac

_build-macos:
	rm -rf dist_app build_app build_bundle/bug-resolution-radar-macos build_bundle/bug-resolution-radar-macos.zip
	$(PYINSTALLER) \
		--noconfirm \
		--clean \
		--windowed \
		--name bug-resolution-radar \
		--icon "$(ICON_ICNS_ABS)" \
		--distpath dist_app \
		--workpath build_app \
		--specpath build_app \
		--add-data "$(PWD)/frontend/dist:frontend_dist" \
		--add-data "$(PWD)/.env.example:." \
		$(PYINSTALLER_COLLECT_ARGS) \
		$(PWD)/run_desktop.py
	@mkdir -p build_bundle/bug-resolution-radar-macos/dist
	@cp -R dist_app/bug-resolution-radar.app build_bundle/bug-resolution-radar-macos/dist/bug-resolution-radar.app
	@cp README.md build_bundle/bug-resolution-radar-macos/README.md
	@if [ -f .env.example ]; then cp .env.example build_bundle/bug-resolution-radar-macos/.env.example; fi
	@ditto -c -k --sequesterRsrc --keepParent build_bundle/bug-resolution-radar-macos build_bundle/bug-resolution-radar-macos.zip

_build-linux:
	rm -rf dist build build_bundle/bug-resolution-radar-linux
	$(PYINSTALLER) \
		--noconfirm \
		--clean \
		--onefile \
		--windowed \
		--name bug-resolution-radar \
		--icon "$(ICON_PNG_ABS)" \
		--workpath build \
		--specpath build \
		--distpath dist \
		--add-data "$(PWD)/frontend/dist:frontend_dist" \
		--add-data "$(PWD)/.env.example:." \
		$(PYINSTALLER_COLLECT_ARGS) \
		$(PWD)/run_desktop.py
	@mkdir -p build_bundle/bug-resolution-radar-linux/dist
	@cp dist/bug-resolution-radar build_bundle/bug-resolution-radar-linux/dist/bug-resolution-radar
	@cp README.md build_bundle/bug-resolution-radar-linux/README.md
	@if [ -f .env.example ]; then cp .env.example build_bundle/bug-resolution-radar-linux/.env.example; fi

kill:
	@set -e; \
	for port in 8000 5173; do \
		if command -v lsof >/dev/null 2>&1; then \
			pids="$$(lsof -ti tcp:$$port -sTCP:LISTEN 2>/dev/null || true)"; \
			if [ -n "$$pids" ]; then kill $$pids 2>/dev/null || true; fi; \
		fi; \
	done; \
	pkill -f "run_api.py" 2>/dev/null || true; \
	pkill -f "run_desktop.py" 2>/dev/null || true; \
	pkill -f "vite --host 127.0.0.1 --port 5173" 2>/dev/null || true; \
	echo "Puertos de desarrollo liberados."

clean:
	rm -rf $(VENV) .mypy_cache .pytest_cache .ruff_cache .coverage htmlcov $(FRONTEND_DIR)/node_modules $(FRONTEND_DIST) dist dist_app build build_app build_bundle
