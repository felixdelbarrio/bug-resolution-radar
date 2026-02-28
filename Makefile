SHELL := /bin/bash

PY ?= python3
VENV ?= .venv
PIP=$(VENV)/bin/pip
PYTHON=$(VENV)/bin/python
RUN=$(VENV)/bin/streamlit
PYTEST=$(VENV)/bin/pytest
PYINSTALLER=$(VENV)/bin/pyinstaller

HOST_UNAME := $(shell uname -s 2>/dev/null || echo unknown)
PPT_REGRESSION_TEST_EXPR = subprocess_with_timeout

PYINSTALLER_COLLECT_ALL_ARGS = \
	--collect-all streamlit \
	--collect-all webview \
	--collect-all watchdog \
	--collect-all plotly \
	--collect-all pptx \
	--collect-all lxml \
	--collect-all PIL \
	--collect-all kaleido \
	--collect-all choreographer \
	--collect-all logistro \
	--collect-all simplejson \
	--collect-all orjson \
	--collect-all openpyxl \
	--collect-all xlsxwriter \
	--collect-all numpy \
	--collect-all browser_cookie3 \
	--collect-all bug_resolution_radar

# Finder/Quick Look can recreate .DS_Store while packaging folders are being removed.
# Retry a few times to make clean targets less flaky on macOS.
define rm_rf_retry
for path in $(1); do \
	if [ ! -e "$$path" ]; then \
		continue; \
	fi; \
	for attempt in 1 2 3; do \
		find "$$path" -name .DS_Store -delete 2>/dev/null || true; \
		if rm -rf "$$path"; then \
			break; \
		fi; \
		sleep 1; \
	done; \
	if [ -e "$$path" ]; then \
		echo "No se pudo eliminar $$path (Finder/Quick Look puede estar recreando .DS_Store)." >&2; \
		exit 1; \
	fi; \
done
endef

.DEFAULT_GOAL := help

.PHONY: help setup format lint typecheck test run clean clean-build \
	ensure-build-tools ensure-desktop-runtime-deps sync-build-env \
	test-ppt-regression build-local build-macos build-linux

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
	@echo "  make test-ppt-regression  Regresión PPT/Kaleido (igual que en workflows POSIX)"
	@echo "  make sync-build-env Sincroniza deps de build/runtime desktop antes de empaquetar"
	@echo "  make build-local Auto-detecta OS (macOS/Linux) y construye binario local"
	@echo "  make build-macos Construye .app + zip local (igual a .github/workflows/build-macos.yml)"
	@echo "  make build-linux Construye binario Linux + bundle local (igual a .github/workflows/build-linux.yml)"
	@echo "  make clean-build Borra artefactos de build de binarios"
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

ensure-build-tools:
	@if [ ! -x "$(PYTHON)" ]; then \
		echo "No se encontró $(PYTHON). Ejecuta: make setup"; \
		exit 1; \
	fi
	@if [ ! -x "$(PYTEST)" ]; then \
		echo "No se encontró $(PYTEST). Ejecuta: make setup"; \
		exit 1; \
	fi
	@if [ ! -x "$(PYINSTALLER)" ]; then \
		echo "No se encontró $(PYINSTALLER). Ejecuta: make setup"; \
		exit 1; \
	fi

ensure-desktop-runtime-deps:
	@$(PYTHON) -c "import importlib.util,sys;missing=[m for m in ('streamlit','webview') if importlib.util.find_spec(m) is None];(sys.stderr.write('Faltan dependencias de runtime desktop: '+', '.join(missing)+'. Ejecuta: make sync-build-env\\n') or sys.exit(2)) if missing else print('Runtime desktop OK (streamlit + webview).')"

sync-build-env: ensure-build-tools
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"
	$(MAKE) ensure-desktop-runtime-deps

test-ppt-regression: ensure-build-tools
	$(PYTEST) -q tests/test_executive_report_ppt.py -k "$(PPT_REGRESSION_TEST_EXPR)"
	$(PYTEST) -q tests/test_run_streamlit_entrypoint.py
	$(PYTEST) -q tests/test_executive_report_ppt.py::test_generate_scope_executive_ppt_is_scoped_and_valid_ppt

build-local:
	@case "$(HOST_UNAME)" in \
		Darwin) $(MAKE) build-macos ;; \
		Linux) $(MAKE) build-linux ;; \
		*) echo "OS no soportado para build-local: $(HOST_UNAME)"; exit 1 ;; \
	esac

build-macos: sync-build-env test-ppt-regression
	@if [ "$(HOST_UNAME)" != "Darwin" ]; then \
		echo "El target build-macos requiere ejecutarse en macOS."; \
		exit 1; \
	fi
	@$(call rm_rf_retry,dist_app build_app build_bundle/bug-resolution-radar-macos bug-resolution-radar-macos.zip)
	ROOT_DIR="$$(pwd)"; \
	EXTRA_ARGS=(); \
	if [ -d src/bug_resolution_radar/ui/assets ]; then \
		EXTRA_ARGS+=(--add-data "$$ROOT_DIR/src/bug_resolution_radar/ui/assets:bug_resolution_radar/ui/assets"); \
	else \
		echo "src/bug_resolution_radar/ui/assets no existe; se omite --add-data de assets UI."; \
	fi; \
	if [ -f .env.example ]; then \
		EXTRA_ARGS+=(--add-data "$$ROOT_DIR/.env.example:."); \
	fi; \
	if [ -f .streamlit/config.toml ]; then \
		EXTRA_ARGS+=(--add-data "$$ROOT_DIR/.streamlit/config.toml:.streamlit"); \
	fi; \
	$(PYINSTALLER) --noconfirm --clean --windowed --name bug-resolution-radar --icon "$$ROOT_DIR/assets/app_icon/bug-resolution-radar.png" --distpath dist_app --workpath build_app --specpath build_app --add-data "$$ROOT_DIR/app.py:." "$${EXTRA_ARGS[@]}" $(PYINSTALLER_COLLECT_ALL_ARGS) "$$ROOT_DIR/run_streamlit.py"
	APP_INFO_PLIST="dist_app/bug-resolution-radar.app/Contents/Info.plist"; \
	if [ -f "$$APP_INFO_PLIST" ]; then \
		/usr/libexec/PlistBuddy -c "Add :NSAppTransportSecurity dict" "$$APP_INFO_PLIST" 2>/dev/null || true; \
		/usr/libexec/PlistBuddy -c "Add :NSAppTransportSecurity:NSAllowsLocalNetworking bool true" "$$APP_INFO_PLIST" 2>/dev/null || /usr/libexec/PlistBuddy -c "Set :NSAppTransportSecurity:NSAllowsLocalNetworking true" "$$APP_INFO_PLIST"; \
		/usr/libexec/PlistBuddy -c "Add :NSAppTransportSecurity:NSAllowsArbitraryLoadsInWebContent bool true" "$$APP_INFO_PLIST" 2>/dev/null || /usr/libexec/PlistBuddy -c "Set :NSAppTransportSecurity:NSAllowsArbitraryLoadsInWebContent true" "$$APP_INFO_PLIST"; \
	fi
	BUNDLE_DIR="build_bundle/bug-resolution-radar-macos"; \
	mkdir -p "$$BUNDLE_DIR/dist"; \
	if [ -d dist_app/bug-resolution-radar.app ]; then \
		cp -R dist_app/bug-resolution-radar.app "$$BUNDLE_DIR/dist/bug-resolution-radar.app"; \
	fi; \
	cp README.md "$$BUNDLE_DIR/README.md"; \
	if [ -f assets/app_icon/bug-resolution-radar.png ]; then \
		mkdir -p "$$BUNDLE_DIR/assets/app_icon"; \
		cp assets/app_icon/bug-resolution-radar.png "$$BUNDLE_DIR/assets/app_icon/bug-resolution-radar.png"; \
	fi; \
	if [ -f .env.example ]; then \
		cp .env.example "$$BUNDLE_DIR/.env.example"; \
	fi; \
	if [ -f .streamlit/config.toml ]; then \
		mkdir -p "$$BUNDLE_DIR/.streamlit"; \
		cp .streamlit/config.toml "$$BUNDLE_DIR/.streamlit/config.toml"; \
	fi
	ditto -c -k --sequesterRsrc --keepParent \
		"build_bundle/bug-resolution-radar-macos" \
		"bug-resolution-radar-macos.zip"
	@echo "Build macOS completado:"
	@echo "  - dist_app/bug-resolution-radar.app"
	@echo "  - bug-resolution-radar-macos.zip"

build-linux: sync-build-env test-ppt-regression
	@if [ "$(HOST_UNAME)" != "Linux" ]; then \
		echo "El target build-linux requiere ejecutarse en Linux."; \
		exit 1; \
	fi
	@$(call rm_rf_retry,dist build build_bundle/bug-resolution-radar-linux)
	ROOT_DIR="$$(pwd)"; \
	EXTRA_ARGS=(); \
	if [ -d src/bug_resolution_radar/ui/assets ]; then \
		EXTRA_ARGS+=(--add-data "$$ROOT_DIR/src/bug_resolution_radar/ui/assets:bug_resolution_radar/ui/assets"); \
	else \
		echo "src/bug_resolution_radar/ui/assets no existe; se omite --add-data de assets UI."; \
	fi; \
	if [ -f .env.example ]; then \
		EXTRA_ARGS+=(--add-data "$$ROOT_DIR/.env.example:."); \
	fi; \
	if [ -f .streamlit/config.toml ]; then \
		EXTRA_ARGS+=(--add-data "$$ROOT_DIR/.streamlit/config.toml:.streamlit"); \
	fi; \
	$(PYINSTALLER) --noconfirm --clean --onefile --windowed --name bug-resolution-radar --icon "$$ROOT_DIR/assets/app_icon/bug-resolution-radar.png" --workpath build --specpath build --add-data "$$ROOT_DIR/app.py:." "$${EXTRA_ARGS[@]}" $(PYINSTALLER_COLLECT_ALL_ARGS) "$$ROOT_DIR/run_streamlit.py"
	BUNDLE_DIR="build_bundle/bug-resolution-radar-linux"; \
	mkdir -p "$$BUNDLE_DIR/dist"; \
	cp dist/bug-resolution-radar "$$BUNDLE_DIR/dist/bug-resolution-radar"; \
	cp README.md "$$BUNDLE_DIR/README.md"; \
	if [ -f assets/app_icon/bug-resolution-radar.desktop ]; then \
		cp assets/app_icon/bug-resolution-radar.desktop "$$BUNDLE_DIR/bug-resolution-radar.desktop"; \
	fi; \
	if [ -f assets/app_icon/bug-resolution-radar.png ]; then \
		mkdir -p "$$BUNDLE_DIR/assets/app_icon"; \
		cp assets/app_icon/bug-resolution-radar.png "$$BUNDLE_DIR/assets/app_icon/bug-resolution-radar.png"; \
	fi; \
	if [ -f .env.example ]; then \
		cp .env.example "$$BUNDLE_DIR/.env.example"; \
	fi; \
	if [ -f .streamlit/config.toml ]; then \
		mkdir -p "$$BUNDLE_DIR/.streamlit"; \
		cp .streamlit/config.toml "$$BUNDLE_DIR/.streamlit/config.toml"; \
	fi
	@echo "Build Linux completado:"
	@echo "  - dist/bug-resolution-radar"
	@echo "  - build_bundle/bug-resolution-radar-linux"

run:
	$(RUN) run app.py

clean-build:
	@$(call rm_rf_retry,dist dist_app build build_app build_bundle bug-resolution-radar-macos.zip bug-resolution-radar.pkg)

clean:
	rm -rf $(VENV) .mypy_cache .pytest_cache .ruff_cache .coverage htmlcov
