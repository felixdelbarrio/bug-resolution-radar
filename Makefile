SHELL := /bin/bash

PY ?= python3
VENV ?= .venv
PIP=$(VENV)/bin/pip
PYTHON=$(VENV)/bin/python
RUN=$(VENV)/bin/streamlit
PYTEST=$(VENV)/bin/pytest
PYINSTALLER=$(VENV)/bin/pyinstaller
PRECOMMIT=$(VENV)/bin/pre-commit

HOST_UNAME := $(shell uname -s 2>/dev/null || echo unknown)
PPT_REGRESSION_TEST_EXPR = subprocess_with_timeout
APPLE_CODESIGN_IDENTITY ?=
APPLE_NOTARY_PROFILE ?=

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

.PHONY: help setup format lint typecheck test test-cov deadcode-private docs-check precommit quality quality-core install-hooks run clean clean-build \
	ensure-build-tools ensure-desktop-runtime-deps sync-build-env \
	test-ppt-regression build-local build-macos build-linux verify-macos-app

help:
	@echo ""
	@echo "Bug Resolution Radar - comandos"
	@echo ""
	@echo "  make setup       Prepara/actualiza el entorno completo (venv + deps dev)"
	@echo "  make run         Arranca la UI (Streamlit) en localhost"
	@echo "  make format      Formatea el código (ruff format)"
	@echo "  make lint        Lint (ruff, si está instalado)"
	@echo "  make typecheck   Typecheck (mypy, si está instalado)"
	@echo "  make test        Tests (pytest, si está instalado)"
	@echo "  make test-cov    Tests con cobertura (fail-under según pyproject.toml)"
	@echo "  make deadcode-private  Detecta helpers privados huérfanos en src"
	@echo "  make docs-check  Valida integridad de documentación y referencias"
	@echo "  make precommit   Ejecuta hooks de pre-commit sobre todo el repo"
	@echo "  make quality     Cadena completa local (precommit + deadcode + docs + mypy + tests)"
	@echo "  make quality-core Alias de make quality"
	@echo "  make install-hooks Instala pre-commit hooks locales"
	@echo "  make test-ppt-regression  Regresión PPT/Kaleido (igual que en workflows POSIX)"
	@echo "  make sync-build-env Sincroniza deps de build/runtime desktop antes de empaquetar"
	@echo "  make build-local Auto-detecta OS (macOS/Linux) y construye binario local"
	@echo "  make build-macos Construye .app + zip local (igual a .github/workflows/build-macos.yml)"
	@echo "  make verify-macos-app Verifica firma/assessment del .app generado"
	@echo "  make build-linux Construye binario Linux + bundle local (igual a .github/workflows/build-linux.yml)"
	@echo "  make clean-build Borra artefactos de build de binarios"
	@echo "  make clean       Borra venv y cachés"
	@echo ""
	@echo "Variables útiles:"
	@echo "  PY=python3       (puedes cambiarlo al invocar: make setup PY=python3.11)"
	@echo "  APPLE_CODESIGN_IDENTITY='Developer ID Application: ...' (opcional)"
	@echo "  APPLE_NOTARY_PROFILE='perfil-notarytool' (opcional; requiere Apple Developer)"
	@echo ""

setup:
	@if [ ! -d $(VENV) ]; then $(PY) -m venv $(VENV); fi
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"
	@echo ""
	@echo "Entorno listo."
	@echo "Activa con: source .venv/bin/activate"

format:
	@if [ -f $(VENV)/bin/ruff ]; then \
		$(VENV)/bin/ruff format . ; \
	else \
		echo "ruff no está instalado en el venv."; \
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

test-cov:
	@if [ -f "$(PYTEST)" ]; then \
		$(PYTEST) -q --cov=bug_resolution_radar --cov-report=term-missing --cov-report=xml ; \
	else \
		echo "pytest no está instalado en el venv."; \
		exit 1; \
	fi

deadcode-private:
	@if [ -x "$(PYTHON)" ]; then \
		$(PYTHON) scripts/check_dead_private_helpers.py ; \
	else \
		echo "No se encontró $(PYTHON). Ejecuta: make setup"; \
		exit 1; \
	fi

docs-check:
	@if [ -x "$(PYTHON)" ]; then \
		$(PYTHON) scripts/check_docs_references.py ; \
	else \
		echo "No se encontró $(PYTHON). Ejecuta: make setup"; \
		exit 1; \
	fi

precommit:
	@if [ -x "$(PRECOMMIT)" ]; then \
		$(PRECOMMIT) run --all-files ; \
	else \
		echo "pre-commit no está instalado en el venv. Ejecuta: make setup"; \
		exit 1; \
	fi

quality: precommit deadcode-private docs-check
	@if [ -x "$(VENV)/bin/mypy" ]; then \
		$(VENV)/bin/mypy src ; \
	else \
		echo "mypy no está instalado en el venv."; \
		exit 1; \
	fi
	@if [ -x "$(PYTEST)" ]; then \
		$(PYTEST) -q --cov=bug_resolution_radar --cov-report=term-missing --cov-report=xml ; \
	else \
		echo "pytest no está instalado en el venv."; \
		exit 1; \
	fi

quality-core: quality

install-hooks:
	@if [ -x "$(VENV)/bin/pre-commit" ]; then \
		$(VENV)/bin/pre-commit install ; \
		echo "pre-commit hooks instalados."; \
	else \
		echo "pre-commit no está instalado en el venv. Ejecuta: make setup"; \
		exit 1; \
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
	fi; \
	APP_PATH="dist_app/bug-resolution-radar.app"; \
	if [ -n "$(APPLE_CODESIGN_IDENTITY)" ]; then \
		echo "Firmando app con identity: $(APPLE_CODESIGN_IDENTITY)"; \
		codesign --force --deep --options runtime --timestamp --sign "$(APPLE_CODESIGN_IDENTITY)" "$$APP_PATH"; \
	else \
		echo "Re-firmando app con firma ad-hoc (sin Apple Developer)."; \
		codesign --force --deep --sign - "$$APP_PATH"; \
	fi; \
	if [ -n "$(APPLE_NOTARY_PROFILE)" ]; then \
		if [ -z "$(APPLE_CODESIGN_IDENTITY)" ]; then \
			echo "APPLE_NOTARY_PROFILE requiere APPLE_CODESIGN_IDENTITY." >&2; \
			exit 1; \
		fi; \
		NOTARY_ZIP="dist_app/bug-resolution-radar-notary.zip"; \
		rm -f "$$NOTARY_ZIP"; \
		ditto -c -k --sequesterRsrc --keepParent "$$APP_PATH" "$$NOTARY_ZIP"; \
		xcrun notarytool submit "$$NOTARY_ZIP" --keychain-profile "$(APPLE_NOTARY_PROFILE)" --wait; \
		xcrun stapler staple "$$APP_PATH"; \
	else \
		echo "Notarización macOS opcional omitida (APPLE_NOTARY_PROFILE vacío)."; \
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

verify-macos-app:
	@if [ "$(HOST_UNAME)" != "Darwin" ]; then \
		echo "verify-macos-app requiere ejecutarse en macOS."; \
		exit 1; \
	fi
	@APP_PATH="dist_app/bug-resolution-radar.app"; \
	if [ ! -d "$$APP_PATH" ]; then \
		echo "No existe $$APP_PATH. Ejecuta primero: make build-macos"; \
		exit 1; \
	fi; \
	echo "== codesign entitlements =="; \
	codesign -d --entitlements :- "$$APP_PATH" 2>&1 || true; \
	echo "== codesign verify =="; \
	codesign --verify --deep --strict --verbose=2 "$$APP_PATH"; \
	echo "== spctl assess =="; \
	if ! spctl --assess --type execute --verbose=4 "$$APP_PATH"; then \
		echo "Aviso: spctl no aprobó el app (esperable si no está notarizada)."; \
	fi

run:
	$(RUN) run app.py

clean-build:
	@$(call rm_rf_retry,dist dist_app build build_app build_bundle bug-resolution-radar-macos.zip bug-resolution-radar.pkg)

clean:
	rm -rf $(VENV) .mypy_cache .pytest_cache .ruff_cache .coverage htmlcov
