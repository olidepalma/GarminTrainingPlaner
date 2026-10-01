# Garmin Training Planner

Proyecto personal para consultar actividad de Garmin Connect, organizar entrenamientos y obtener propuestas de planificación adaptativa para carrera, trail, ciclismo, natación y triatlón, con fuerza opcional.

Estado: panel privado local con acceso por contraseña, Garmin incremental, autorización oficial de ChatGPT Pro y coach multideporte. Permite guardar un perfil, un objetivo principal y varias pruebas secundarias, generar y editar un borrador de siete días y aceptarlo en el calendario. La planificación de temporada se presenta como estructura textual. Calendario mensual conjunto de propuestas, actividades Garmin y pruebas, con detalles por entrada. Estadísticas y tendencias de VO₂ máx. Biblioteca privada con versiones EPUB/PDF/DOCX/TXT/Markdown, extracción y selección manuales, fragmentos citables y revisión semanal por disciplina. Editor de sesiones por bloques y envío explícito a Garmin Connect para sincronizarlas con el reloj. [Uso y límites](docs/ENTRENAMIENTOS_GARMIN.md).

Decisiones de la usuaria: utilizar su cuenta ChatGPT Pro y desplegar posteriormente en un LXC de Proxmox. Desarrollo nativo en Windows y macOS con Python 3.12, sin Docker obligatorio.

## Inicio rápido

Instala Python 3.12 y uv (versión usada: 0.12.21). En Windows: `winget install --id astral-sh.uv -e`. En macOS, si usas Homebrew: `brew install uv`. Hay una alternativa con pip en la [guía de desarrollo](docs/DESARROLLO.md).

Desde la raíz del proyecto, los comandos son iguales en Windows y macOS:

```text
uv sync --locked
uv run --locked python -m garmin_planner doctor
uv run --locked python -m garmin_planner serve --reload
```

Abre http://127.0.0.1:8000. Las rutas de documentación de la API están desactivadas. Detén el servidor con Ctrl+C. `uv` puede descargar Python 3.12 si no está instalado.

La configuración por defecto funciona sin `.env`. Para personalizar el puerto, copia `.env.example` a `.env`. El lanzador usa acceso local por defecto. El despliegue LXC con dominio HTTPS, proxy inverso y systemd está documentado en [docs/LXC.md](docs/LXC.md).

```text
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
```

- [Desarrollo en Windows y macOS, alternativa requirements y mantenimiento](docs/DESARROLLO.md).
- [Destino LXC de Proxmox](docs/LXC.md).
- [Integración con la cuenta Pro: alcance y siguiente paso](docs/CHATGPT_PRO.md).

El diseño y las fases de implementación están en [docs/PROPUESTA.md](docs/PROPUESTA.md).

## Probar el coach

Abre **Coach y objetivos**. Consulta los modelos de tu cuenta, completa perfil y disponibilidad por día, añade las pruebas y marca exactamente una como principal. Guarda el perfil, elige el inicio y genera un borrador. Revisa estructura, motivos y sesiones antes de guardar la semana. La generación usa Pro solo al pulsar el botón; no hay regeneración semanal automática. Consulta [la guía del coach](docs/COACH.md).

## Biblioteca y revisión semanal

Abre **Biblioteca**, sube el documento y pulsa **Procesar documento**. Revisa la muestra y marca **Usar en el coach**. Para actualizarlo, selecciona la fuente existente antes de subir el nuevo archivo; la versión anterior se mantiene hasta procesar la actualización. Ninguno de estos pasos llama a OpenAI ni modifica el calendario. Puedes subir ya tu EPUB desde esta pestaña. Consulta [la guía de la biblioteca](docs/BIBLIOTECA.md).

En **Coach y objetivos** puedes comparar minutos y sesiones planificadas con actividades registradas por disciplina, ver variaciones de volumen respecto a semanas previas y guardar tus sensaciones. La generación incorpora ese resumen, las estadísticas Garmin habilitadas y hasta seis extractos locales de las fuentes seleccionadas. Las referencias enviadas y las citadas aparecen en el borrador.

## Principios

- Datos y calendario persistentes bajo control de la usuaria.
- Sincronización incremental y recuperable.
- Plan general hasta el objetivo y revisión semanal de sesiones concretas.
- Cálculos locales y contexto acotado para el modelo.
- Los borradores no modifican el calendario hasta su aceptación explícita; aceptar reemplaza las sesiones planificadas de esa semana.
- Autenticación y autorización antes de publicar cualquier dato personal.
- Despliegue reproducible en Proxmox y copias de seguridad fuera del repositorio.

## Git y portabilidad

Este repositorio contiene código, dependencias bloqueadas, documentación, configuración de ejemplo y pruebas. Los datos, credenciales, tokens y backups se almacenarán fuera de Git. `uv.lock` es la referencia de versiones; `requirements.txt` es una exportación para pip. Crea una `.venv` propia en cada equipo; no copies la de otro sistema operativo.

Mover el código con Git no mueve la base de datos ni las sesiones de Garmin. El despliegue deberá documentar también la restauración de volúmenes, base de datos y secretos. No se ha creado un repositorio remoto.
