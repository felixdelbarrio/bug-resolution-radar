SHELL := /bin/bash

PY ?= python3
VENV ?= .venv
PIP=$(VENV)/bin/pip
PYTHON=$(VENV)/bin/python
RUN=$(VENV)/bin/streamlit
PYTEST=$(VENV)/bin/pytest
BLACK=$(VENV)/bin/black
PYINSTALLER=$(VENV)/bin/pyinstaller
PLAYWRIGHT=$(VENV)/bin/playwright
PLAYWRIGHT_BROWSERS ?= chromium

HOST_UNAME := $(shell uname -s 2>/dev/null || echo unknown)
APPLE_CODESIGN_IDENTITY ?=
APPLE_NOTARY_PROFILE ?=
PYINSTALLER_RETRIES ?= 4

PYINSTALLER_BUNDLE_ARGS = \
	--collect-all bug_resolution_radar \
	--collect-data streamlit \
	--collect-data webview \
	--collect-data plotly \
	--collect-data kaleido \
	--collect-data choreographer \
	--collect-data browser_cookie3 \
	--collect-submodules streamlit.runtime.scriptrunner \
	--collect-submodules streamlit.runtime.scriptrunner_utils \
	--copy-metadata streamlit \
	--copy-metadata pywebview \
	--copy-metadata plotly \
	--copy-metadata kaleido

PYINSTALLER_NON_WINDOWS_EXCLUDE_ARGS = \
	--exclude-module pandas.io.clipboard \
	--exclude-module dateutil.tz.win \
	--exclude-module webview.platforms.android \
	--exclude-module webview.platforms.cef \
	--exclude-module webview.platforms.edgechromium \
	--exclude-module webview.platforms.mshtml \
	--exclude-module webview.platforms.winforms \
	--exclude-module click._winconsole

# Finder/Quick Look can recreate .DS_Store while packaging folders are being removed.
# Retry a few times to make clean targets less flaky on macOS.
define rm_rf_retry
for path in $(1); do \
	if [ ! -e "$$path" ]; then \
		continue; \
	fi; \
	for attempt in 1 2 3 4 5; do \
		if [ ! -e "$$path" ]; then \
			break; \
		fi; \
		find "$$path" \( -name .DS_Store -o -name "Icon?" \) -delete 2>/dev/null || true; \
		if [ "$$(uname -s 2>/dev/null || echo unknown)" = "Darwin" ]; then \
			chflags -R nouchg "$$path" 2>/dev/null || true; \
		fi; \
		chmod -R u+w "$$path" 2>/dev/null || true; \
		rm -rf "$$path" 2>/dev/null || true; \
		if [ ! -e "$$path" ]; then \
			break; \
		fi; \
		if [ -d "$$path" ]; then \
			find "$$path" -mindepth 1 -exec rm -rf {} + 2>/dev/null || true; \
			rmdir "$$path" 2>/dev/null || true; \
		fi; \
		if [ ! -e "$$path" ]; then \
			break; \
		fi; \
		sleep 1; \
	done; \
	if [ -e "$$path" ]; then \
		echo "No se pudo eliminar $$path tras varios intentos (posible bloqueo de Finder/Quick Look)." >&2; \
		ls -la "$$path" 2>/dev/null || true; \
		exit 1; \
	fi; \
done
endef

.DEFAULT_GOAL := help

.PHONY: help setup CI all-github-actions test run clean build build-local make.build \
	_ensure-build-tools _ensure-desktop-runtime-deps _sync-build-env \
	_test-ppt-regression _build-macos _build-linux _verify-macos-app _clean-build

help:
	@echo ""
	@echo "Bug Resolution Radar - comandos"
	@echo ""
	@echo "  make setup       Prepara/actualiza el entorno completo (venv + deps dev)"
	@echo "  make CI          Ejecuta la cadena CI (ruff+black/lint/typecheck/tests/docs/deadcode)"
	@echo "  make run         Arranca la UI (Streamlit) en localhost"
	@echo "  make test        Ejecuta tests del repo (pytest)"
	@echo "  make build       Flujo único de build: limpia + sync entorno + regresión PPT + build OS (macOS incluye verify)"
	@echo "  make make.build  Alias explícito del target de build"
	@echo "  make build-local Alias legado (compatibilidad)"
	@echo "  make clean       Borra venv y cachés"
	@echo ""
	@echo "Variables útiles:"
	@echo "  PY=python3       (puedes cambiarlo al invocar: make setup PY=python3.11)"
	@echo "  INSTALL_PLAYWRIGHT=1 (opcional; instala navegador Chromium de Playwright en setup)"
	@echo "  APPLE_CODESIGN_IDENTITY='Developer ID Application: ...' (opcional)"
	@echo "  APPLE_NOTARY_PROFILE='perfil-notarytool' (opcional; requiere Apple Developer)"
	@echo ""

setup:
	@if [ ! -d $(VENV) ]; then $(PY) -m venv $(VENV); fi
	$(PIP) install -U pip
	$(PIP) install -r requirements-dev.txt
	@if [ "$(INSTALL_PLAYWRIGHT)" = "1" ] && [ -x "$(PLAYWRIGHT)" ]; then \
		$(PLAYWRIGHT) install $(PLAYWRIGHT_BROWSERS); \
	else \
		echo "Playwright browsers omitidos (usa INSTALL_PLAYWRIGHT=1 para instalarlos)."; \
	fi
	@echo ""
	@echo "Entorno listo."
	@echo "Activa con: source .venv/bin/activate"

test:
	@if [ ! -x "$(PYTEST)" ]; then \
		echo "pytest no está instalado en el venv. Ejecuta: make setup"; \
		exit 1; \
	fi
	@$(PYTEST) -q

CI:
	@if [ ! -x "$(PYTHON)" ]; then \
		echo "No se encontró $(PYTHON). Ejecuta: make setup"; \
		exit 1; \
	fi
	@if [ ! -x "$(BLACK)" ]; then \
		echo "black no está instalado en el venv. Ejecuta: make setup"; \
		exit 1; \
	fi
	@if [ ! -x "$(VENV)/bin/ruff" ]; then \
		echo "ruff no está instalado en el venv. Ejecuta: make setup"; \
		exit 1; \
	fi
	@if [ ! -x "$(VENV)/bin/mypy" ]; then \
		echo "mypy no está instalado en el venv. Ejecuta: make setup"; \
		exit 1; \
	fi
	@if [ ! -x "$(PYTEST)" ]; then \
		echo "pytest no está instalado en el venv. Ejecuta: make setup"; \
		exit 1; \
	fi
	@echo "[1/7] ruff format --check ."
	@$(VENV)/bin/ruff format --check .
	@echo "[2/7] black --check ."
	@$(BLACK) --check .
	@echo "[3/7] ruff check ."
	@$(VENV)/bin/ruff check .
	@echo "[4/7] mypy src"
	@$(VENV)/bin/mypy src
	@echo "[5/7] dead private helper guard"
	@$(PYTHON) scripts/check_dead_private_helpers.py
	@echo "[6/7] docs references guard"
	@$(PYTHON) scripts/check_docs_references.py
	@echo "[7/7] pytest --cov"
	@$(PYTEST) -q --cov=bug_resolution_radar --cov-report=term-missing --cov-report=xml
	@echo "CI completado."

all-github-actions:
	@echo "Target 'all-github-actions' deprecado; usa 'make CI'."
	@$(MAKE) CI

_ensure-build-tools:
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

_ensure-desktop-runtime-deps:
	@$(PYTHON) -c "import importlib.util,sys;mods=('streamlit','webview','plotly','kaleido','choreographer','pptx');missing=[m for m in mods if importlib.util.find_spec(m) is None];(sys.stderr.write('Faltan dependencias críticas de runtime/reporting: '+', '.join(missing)+'. Ejecuta: make setup\\n') or sys.exit(2)) if missing else print('Runtime/reporting OK ('+', '.join(mods)+').')"

_sync-build-env: _ensure-build-tools
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"
	$(MAKE) _ensure-desktop-runtime-deps

_test-ppt-regression: _ensure-build-tools
	$(PYTEST) -q tests/test_run_streamlit_entrypoint.py
	$(PYTEST) -q tests/test_executive_report_ppt.py

build: make.build

make.build: _clean-build _sync-build-env _test-ppt-regression
	@case "$(HOST_UNAME)" in \
		Darwin) \
			$(MAKE) _build-macos; \
			$(MAKE) _verify-macos-app; \
			;; \
		Linux) \
			$(MAKE) _build-linux; \
			;; \
		*) \
			echo "OS no soportado para build: $(HOST_UNAME)"; \
			exit 1; \
			;; \
	esac

build-local:
	@echo "Target 'build-local' deprecado; usa 'make build'."
	@$(MAKE) make.build

_build-macos:
	@if [ "$(HOST_UNAME)" != "Darwin" ]; then \
		echo "El target build-macos requiere ejecutarse en macOS."; \
		exit 1; \
	fi
	@$(call rm_rf_retry,dist_app build_app build_bundle/bug-resolution-radar-macos build_bundle/bug-resolution-radar-macos.zip bug-resolution-radar-macos.zip)
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
	if [ -f .env ]; then \
		EXTRA_ARGS+=(--add-data "$$ROOT_DIR/.env:."); \
	fi; \
	if [ -f .streamlit/config.toml ]; then \
		EXTRA_ARGS+=(--add-data "$$ROOT_DIR/.streamlit/config.toml:.streamlit"); \
	fi; \
	BUILD_OK=0; \
	for attempt in $$(seq 1 $(PYINSTALLER_RETRIES)); do \
		ATTEMPT_WORK="build_app_attempt_$$attempt"; \
		ATTEMPT_DIST="dist_app_attempt_$$attempt"; \
		rm -rf "$$ATTEMPT_WORK" "$$ATTEMPT_DIST" bug-resolution-radar.pkg; \
		if $(PYINSTALLER) --noconfirm --clean --windowed --name bug-resolution-radar --icon "$$ROOT_DIR/assets/app_icon/bug-resolution-radar.png" --distpath "$$ATTEMPT_DIST" --workpath "$$ATTEMPT_WORK" --specpath "$$ATTEMPT_WORK" --add-data "$$ROOT_DIR/app.py:." "$${EXTRA_ARGS[@]}" $(PYINSTALLER_BUNDLE_ARGS) $(PYINSTALLER_NON_WINDOWS_EXCLUDE_ARGS) "$$ROOT_DIR/run_streamlit.py"; then \
			rm -rf dist_app build_app; \
			mv "$$ATTEMPT_DIST" dist_app; \
			mv "$$ATTEMPT_WORK" build_app; \
			BUILD_OK=1; \
			break; \
		fi; \
		rm -rf "$$ATTEMPT_WORK" "$$ATTEMPT_DIST" bug-resolution-radar.pkg; \
		if [ "$$attempt" -ge "$(PYINSTALLER_RETRIES)" ]; then \
			echo "PyInstaller falló tras $$attempt intentos." >&2; \
			exit 1; \
		fi; \
		echo "PyInstaller falló (intento $$attempt). Reintentando build limpio..." >&2; \
		sleep 1; \
	done; \
	if [ "$$BUILD_OK" -ne 1 ]; then \
		echo "PyInstaller no completó el build." >&2; \
		exit 1; \
	fi
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
	ZIP_PATH="build_bundle/bug-resolution-radar-macos.zip"; \
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
	if [ -f .env ]; then \
		cp .env "$$BUNDLE_DIR/.env"; \
	fi; \
	if [ -f .streamlit/config.toml ]; then \
		mkdir -p "$$BUNDLE_DIR/.streamlit"; \
		cp .streamlit/config.toml "$$BUNDLE_DIR/.streamlit/config.toml"; \
	fi
	rm -f "$$ZIP_PATH" bug-resolution-radar-macos.zip; \
	ditto -c -k --sequesterRsrc --keepParent \
		"build_bundle/bug-resolution-radar-macos" \
		"$$ZIP_PATH"
	@echo "Build macOS completado:"
	@echo "  - dist_app/bug-resolution-radar.app"
	@echo "  - build_bundle/bug-resolution-radar-macos.zip"

_build-linux:
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
	if [ -f .env ]; then \
		EXTRA_ARGS+=(--add-data "$$ROOT_DIR/.env:."); \
	fi; \
	if [ -f .streamlit/config.toml ]; then \
		EXTRA_ARGS+=(--add-data "$$ROOT_DIR/.streamlit/config.toml:.streamlit"); \
	fi; \
	$(PYINSTALLER) --noconfirm --clean --onefile --windowed --name bug-resolution-radar --icon "$$ROOT_DIR/assets/app_icon/bug-resolution-radar.png" --workpath build --specpath build --add-data "$$ROOT_DIR/app.py:." "$${EXTRA_ARGS[@]}" $(PYINSTALLER_BUNDLE_ARGS) $(PYINSTALLER_NON_WINDOWS_EXCLUDE_ARGS) "$$ROOT_DIR/run_streamlit.py"
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
	if [ -f .env ]; then \
		cp .env "$$BUNDLE_DIR/.env"; \
	fi; \
	if [ -f .streamlit/config.toml ]; then \
		mkdir -p "$$BUNDLE_DIR/.streamlit"; \
		cp .streamlit/config.toml "$$BUNDLE_DIR/.streamlit/config.toml"; \
	fi
	@echo "Build Linux completado:"
	@echo "  - dist/bug-resolution-radar"
	@echo "  - build_bundle/bug-resolution-radar-linux"

_verify-macos-app:
	@if [ "$(HOST_UNAME)" != "Darwin" ]; then \
		echo "verify-macos-app requiere ejecutarse en macOS."; \
		exit 1; \
	fi
	@APP_PATH="dist_app/bug-resolution-radar.app"; \
	if [ ! -d "$$APP_PATH" ]; then \
		echo "No existe $$APP_PATH. Ejecuta primero: make build"; \
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
	$(PYTHON) run_streamlit.py

_clean-build:
	@$(call rm_rf_retry,dist dist_app build build_app build_bundle bug-resolution-radar-macos.zip bug-resolution-radar.pkg)

clean:
	rm -rf $(VENV) .mypy_cache .pytest_cache .ruff_cache .coverage htmlcov
