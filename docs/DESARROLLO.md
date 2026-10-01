# Entorno de desarrollo

## Herramientas y alcance

Usamos Python **3.12** en todos los equipos para reducir diferencias, `uv` para entorno virtual/dependencias y Git para el código. No hacen falta Docker, Node, PostgreSQL, cuenta Garmin o credenciales de OpenAI para probar esta base. La persistencia SQLite, el acceso por contraseña y las integraciones ya están disponibles. Las pruebas usan cuentas simuladas; para usar las integraciones reales debes conectarlas desde la web.

- `pyproject.toml`: metadatos, rangos de dependencias y herramientas.
- `.python-version`: versión de Python del proyecto.
- `uv.lock`: versiones exactas y artefactos de las plataformas soportadas.
- `requirements.txt`: exportación del entorno base con herramientas de desarrollo.
- `.env.example`: opciones locales sin secretos; `.env` es privado.
- `src/garmin_planner`: paquete instalable, servidor y panel privado.
- `tests`: comprobaciones del entorno y de los límites locales.

## Windows (PowerShell)

Instala Python 3.12 desde python.org si prefieres gestionarlo tú. Instala uv con:

```powershell
winget install --id astral-sh.uv -e
```

Abre una terminal nueva para actualizar PATH y entra en la carpeta del proyecto. Ejecuta:

```powershell
uv sync --locked
uv run --locked python -m garmin_planner doctor
uv run --locked python -m garmin_planner serve --reload
```

No es necesario activar `.venv`, usar WSL ni cambiar la política de ejecución de PowerShell. uv selecciona Python 3.12 y puede descargarlo si falta. Si quieres instalar uv con un Python ya disponible en lugar de winget:

```powershell
py -3.12 -m pip install --user uv==0.12.21
py -3.12 -m uv sync --locked
py -3.12 -m uv run --locked python -m garmin_planner serve --reload
```

## macOS (Terminal)

Si utilizas Homebrew:

```sh
brew install uv
```

Desde la raíz del proyecto:

```sh
uv sync --locked
uv run --locked python -m garmin_planner doctor
uv run --locked python -m garmin_planner serve --reload
```

Alternativamente, con Python 3.12 instalado, puedes instalar uv aislado dentro del proyecto:

```sh
python3.12 -m venv .tooling
.tooling/bin/python -m pip install uv==0.12.21
.tooling/bin/uv sync --locked
.tooling/bin/uv run --locked python -m garmin_planner serve --reload
```

Los ejemplos siguientes usan `uv`; si eliges la instalación aislada, sustituye ese comando por `.tooling/bin/uv`.

## Comprobar el resultado

Abre http://127.0.0.1:8000. Debes ver el acceso al panel. `/api/health` devuelve JSON y `/docs` está desactivado. La interfaz utiliza archivos locales sin CDN; las integraciones realizan peticiones a Garmin/OpenAI al conectarlas y utilizarlas.

```text
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m garmin_planner doctor
```

Pruebas verificadas localmente en macOS con Python 3.12. Se incluye un workflow para Windows, macOS y Linux; solo se ejecutará cuando haya un repositorio remoto en GitHub. Hasta entonces Windows y LXC no están verificados en máquinas reales.

## Configuración opcional

No hace falta crear `.env` para iniciar. Para modificarlo:

macOS:

```sh
cp .env.example .env
```

Windows:

```powershell
Copy-Item .env.example .env
```

Ejemplo: `GTP_PORT=8123` cambia la URL a http://127.0.0.1:8123. Reinicia el servidor después de cambiar `.env`. Ejecuta siempre desde la raíz, donde se busca el archivo. `GTP_HOST` solo permite loopback. `GTP_TIMEZONE` usa un identificador IANA; se instala `tzdata` también en Windows.

`GTP_COACH_PROVIDER=chatgpt_pro` registra la elección de proveedor. **No autentica ni activa llamadas**. No hay API de pago alternativa ni claves API requeridas.

## Alternativa clásica con requirements y pip

`requirements.txt` se genera desde el lock e incluye herramientas de desarrollo, pero no el extra Garmin. No lo edites a mano. Usa una `.venv` nueva para esta alternativa y no mezcles gestores en ella.

macOS:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m garmin_planner doctor
.venv/bin/python -m garmin_planner serve --reload
```

Windows:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install --no-deps -e .
.venv\Scripts\python.exe -m garmin_planner doctor
.venv\Scripts\python.exe -m garmin_planner serve --reload
```

La instalación editable permite ver los cambios sin reinstalar el paquete. Con pip, los tests se ejecutan mediante el Python de `.venv` y `-m pytest`; Ruff admite `-m ruff check .`.

## Extra Garmin

Para preparar las dependencias de la próxima fase:

```text
uv sync --locked --extra garmin
uv run --locked --extra garmin python -m garmin_planner doctor
```

Instalar la librería **no conecta la cuenta**. El adaptador y el flujo MFA están implementados; conecta la cuenta desde la pestaña Conexiones. Garmin ya es una dependencia base: no necesitas el extra `garmin`.

## Trabajar entre dos ordenadores

Comparte el código mediante un repositorio Git remoto de tu elección o una copia de la carpeta sin `.venv`, `.tooling`, `.env`, datos y tokens. El remoto todavía no está creado.

Cuando exista un remoto, guarda y sube tus cambios desde un equipo, recíbelos en el otro y ejecuta `uv sync --locked` antes de continuar. Versiona conjuntamente `pyproject.toml`, `uv.lock` y `requirements.txt` cuando cambien dependencias. Los cambios locales sin commit no se trasladan con Git.

Cada equipo tendrá su propio entorno y, cuando implementemos OAuth, sus propias credenciales protegidas. No compartas tokens mediante Git o carpetas públicas.

## Actualizar dependencias deliberadamente

Después de editar `pyproject.toml`:

```text
uv lock
uv sync --locked
uv export --locked --no-emit-project --output-file requirements.txt
uv run --locked pytest
uv run --locked ruff check .
```

Para actualizar versiones existentes deliberadamente, usa `uv lock --upgrade` y revisa los cambios. Para formatear código: `uv run --locked ruff format .`.

## Problemas frecuentes

- **Puerto ocupado:** modifica `GTP_PORT` en `.env` y reinicia.
- **uv no aparece:** abre una terminal nueva o utiliza la alternativa `python -m uv`.
- **Python incorrecto con pip:** usa explícitamente Python 3.12; uv lo selecciona por `.python-version`.
- **Error de lock:** usa `uv lock` solo si has cambiado dependencias; en el segundo equipo trae también el lock actualizado.
- **Cambios de zona horaria:** usa nombres como `Europe/Madrid`, no abreviaturas como CET.
- **Sin Internet:** la primera instalación necesita descargar paquetes. Las pruebas posteriores no consultan cuentas externas.

Fuentes: [instalación uv](https://docs.astral.sh/uv/getting-started/installation/) y [lock/sincronización](https://docs.astral.sh/uv/concepts/projects/sync/).
