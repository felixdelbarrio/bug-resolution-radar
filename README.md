# Bug Resolution Radar (Jira-only)
**Un dashboard local para dar visibilidad real a tu backlog de bugs en Jira — sin montar infraestructura, sin servidores y sin tocar tu instancia de Jira.**

Bug Resolution Radar convierte tu lista de incidencias en un **panel ejecutivo y operativo** para priorizar mejor, detectar cuellos de botella y entender el estado del producto en minutos. Corre **en tu máquina** y se conecta directamente a Jira usando tu sesión (cookie) o un fallback manual, guardando los datos **en local**.

---

## ¿Para qué sirve?
- **Visibilidad inmediata**: cuántas incidencias siguen abiertas, cuáles crecen, cuáles se estancan.
- **Priorización basada en datos**: filtros por criticidad, estado, tipo, componente y asignado.
- **KPIs de resolución**: nuevas vs cerradas, tiempo medio de resolución, % de abiertas con antigüedad > X días.
- **Tendencias**: evolución de los últimos 90 días y distribución de antigüedad del backlog.
- **Operación sin fricción**: no requiere backend ni despliegues. Ideal para equipos pequeños/medianos o para análisis rápido.

---

## Qué NO hace (a propósito)
- No escribe cambios en Jira (solo lectura).
- No envía telemetría ni datos a terceros.
- No requiere API propia ni servicios adicionales.

---

## Cómo funciona
1. Configuras tu **Jira Base URL** y el **Project Key** (y opcionalmente un JQL).
2. La app se autentica **con tu sesión del navegador** (Chrome/Edge) o con un **cookie manual en memoria**.
3. Descarga issues desde Jira REST API y las guarda en `data/issues.json`.
4. Muestra un dashboard interactivo con KPIs y filtros.

---

## Requisitos
- **Python 3.9+** (recomendado 3.11 también funciona)
- **Chrome o Edge** (para lectura de cookie Jira en modo automático)
- Conectividad a tu instancia de Jira (Cloud / Server con REST compatible)

---

## Instalación y ejecución

### Linux
1) Instala Python 3 y venv (si no lo tienes):
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip make
```

2) En la carpeta del proyecto:
```bash
make setup
make run
```

> Si tu sistema no tiene `make`, instala `make` o usa los comandos manuales del apartado “Sin Make”.

---

### macOS
1) Asegura Python 3 y make (normalmente ya viene make con Xcode Command Line Tools):
```bash
xcode-select --install
python3 --version
```

2) En la carpeta del proyecto:
```bash
make setup
make run
```

---

### Windows (recomendado con PowerShell)
1) Instala Python 3 desde el instalador oficial (marca “Add Python to PATH”).
2) Instala `make` (opciones):
- **Opción A**: usar **WSL** (recomendado): instala Ubuntu desde Microsoft Store, y sigue la guía de Linux.
- **Opción B**: instalar `make` con Chocolatey:
  ```powershell
  choco install make
  ```

3) En la carpeta del proyecto (PowerShell):
```powershell
make setup
make run
```

> Si no quieres instalar `make`, usa el método “Sin Make” (abajo).

---

## Ejecución sin Make (Linux/macOS/Windows)
En la raíz del proyecto:

### Linux/macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
streamlit run app.py
```

### Windows (PowerShell)
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -e ".[dev]"
streamlit run app.py
```

---

## Configuración
La primera vez, se crea un `.env` a partir de `.env.example`.

Valores clave:
- `JIRA_BASE_URL` → Ej: `https://tu-dominio.atlassian.net`
- `JIRA_PROJECT_KEY` → Ej: `ABC`
- `JIRA_JQL` (opcional) → si lo dejas vacío usa: `project = "<KEY>" ORDER BY updated DESC`
- `JIRA_COOKIE_DOMAIN` → dominio del Jira (ej: `tu-dominio.atlassian.net`)
- `JIRA_BROWSER` → `chrome` o `edge`

---

## Uso
1) Abre la app (Streamlit) en `http://localhost:8501`
2) Pestaña **Configuración**: rellena Jira URL, Project Key, dominio y navegador.
3) Pestaña **Ingesta**:
   - **Test conexión Jira**
   - **Reingestar Jira ahora**
   - Si falla la cookie automática, pega el header `Cookie` manualmente (solo memoria).
4) Pestaña **Dashboard**: aplica filtros, revisa KPIs y tendencias, añade notas locales.

---

## Privacidad y seguridad
- La app corre localmente.
- No hay backend ni servicios externos.
- La cookie Jira **no se guarda**: solo se usa en memoria para autenticar la sesión.
- Los datos se guardan en local: `data/issues.json` y `data/notes.json`.

---

## Comandos útiles
```bash
make        # muestra ayuda
make setup  # crea venv + instala deps
make run    # lanza dashboard
make test   # tests
make lint   # ruff
make format # black
make clean  # borra venv y cachés
```

---

## Soporte / troubleshooting
- Si la lectura automática de cookie falla, usa el campo “Fallback: pegar cookie manualmente” en la pestaña Ingesta.
- Si `make` da errores por `python`/`python3`, prueba:
  ```bash
  make setup PY=python3
  ```

---
