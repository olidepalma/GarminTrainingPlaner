# Organización del proyecto

La aplicación mantiene FastAPI, Python 3.12 y SQLite. El servidor valida permisos y datos, integra Garmin/OpenAI y construye el contexto del coach. La interfaz muestra resultados y recoge acciones. No se incluye lógica del coach ni credenciales en el JavaScript.

## Servidor

`app.py` construye la aplicación, prepara los servicios, la sincronización nocturna y las protecciones de sesión, Origin y encabezados. `api/` separa los routers de acceso, Garmin, Pro, calendario, coach, biblioteca, trabajos y sesiones. `api/schemas.py` contiene los contratos de las peticiones. Cada router conserva la comprobación de autenticación del servidor; ocultar un botón no determina permisos.

Los servicios existentes (`coach.py`, `garmin.py`, `library.py`, `workouts.py`) concentran sus reglas y llamadas externas. `storage.py` proporciona transacciones y acceso a SQLite; `planned_sessions.py` gestiona las sesiones del coach y su migración. El registro explícito de routers está en `api/routing.py`.

## Interfaz

`static/app.js` es el punto de entrada de módulos ES. `static/modules/` separa acceso, conexiones, vista general, estadísticas, coach, calendario, editor de sesiones, revisión y biblioteca. `core.js` contiene las peticiones HTTP, estado de sesión, formato y controles comunes. Cada módulo registra sus eventos mediante `init()`; el punto de entrada coordina arranque y refresco.

Los módulos no exponen funciones en `window` y comparten dependencias mediante imports explícitos. El navegador sigue descargando JavaScript: es código de interfaz, no una barrera de seguridad. No se necesita Node.js ni un compilador frontend en el LXC. La comprobación de sintaxis de desarrollo/CI utiliza `python scripts/check_frontend.py` con Node instalado.

## Sesiones y migración

- `planned_sessions`: una fila por sesión del coach aceptada o en borrador, con UUID estable, origen/estado, identificador de plan, fecha, deporte, nombre, minutos e indicaciones. Los detalles variables (bloques, fuerza y otras propiedades) permanecen en JSON por sesión.
- `workouts`: sesiones propias y registros de envío a Garmin. Se conservan sus identificadores remotos y estados.
- `activities`: actividades importadas; no se convierten automáticamente en cumplimiento de una propuesta.
- `coach_history`: instantáneas completas de las decisiones aceptadas, adecuadas para auditoría.
- `meta`: configuración, encabezado del borrador, referencias y otras preferencias; ya no contiene el calendario activo del coach como una lista monolítica.

La migración `planned_sessions_v1` se ejecuta una vez al abrir la base. Copia el calendario y las sesiones del borrador a filas, conserva el texto y los detalles, y guarda los JSON originales en `legacy_coach_calendar_v1` y `legacy_coach_draft_v1`. La misma transacción registra la versión: si falla, se revierte. Reiniciar no vuelve a importar ni duplica filas. El calendario y la revisión semanal consultan sesiones por fechas con índices.

Aceptar una semana reemplaza solo las sesiones aceptadas de esas fechas; mantiene los identificadores de las otras semanas y las propuestas propias. Borrar desactiva una fila y conserva un registro; el histórico aceptado permanece inmutable. Los formatos de la API se mantienen para conservar compatibilidad con la interfaz y las integraciones.

## Actualizar el LXC

Antes de esta versión, realiza un respaldo del directorio completo de datos con el servicio detenido. El script `deploy/update-lxc.sh` lo hace antes de arrancar el nuevo código. Desde el checkout actualizado:

```sh
cd /opt/GarminTrainingPlaner
git pull --ff-only
bash deploy/update-lxc.sh
```

La migración se realiza al iniciar el servicio. Después verifica login, calendario, borrador, biblioteca y conexiones; recarga la pestaña para cargar los módulos nuevos. No requiere volver a conectar Garmin/Pro ni volver a subir documentos. Para volver a una versión anterior, detén el servicio y restaura juntos código y respaldo de datos: un simple rollback de Git no revierte el esquema ni la ubicación del calendario.
