# Despliegue en LXC con dominio HTTPS

La aplicación usa Python 3.12, SQLite, documentos y secretos cifrados en un directorio privado. No necesita Docker, PostgreSQL ni un worker aparte. El mismo proceso mantiene la sincronización nocturna. Ejecuta una sola instancia/worker para evitar tareas duplicadas. Usa un LXC no privilegiado con systemd, conexión saliente HTTPS, reloj correcto y almacenamiento persistente. Como punto de partida: 2 CPU, 2 GB RAM y disco según documentos y copias; ajustar con uso real.

## Preparar el contenedor

Comandos para un LXC basado en Debian/Ubuntu; concretar distribución, SSH, dominio y proxy antes de ejecutar. Ejecutar como root en el LXC:

```sh
apt update
apt install -y git python3 python3-venv ca-certificates openssh-server
useradd --system --home-dir /var/lib/garmin-planner --create-home --shell /usr/sbin/nologin garmin-planner
install -d -m 0755 /opt/GarminTrainingPlaner /opt/gtp-tools
install -d -m 0700 -o garmin-planner -g garmin-planner /var/lib/garmin-planner
install -d -m 0750 /etc/garmin-planner
python3 -m venv /opt/gtp-tools
/opt/gtp-tools/bin/pip install uv==0.12.21
```

`useradd` solo se ejecuta en la instalación inicial. El código se copia a `/opt/GarminTrainingPlaner` mediante Git o SCP, sin `.venv`, `.env`, `data` ni archivos de desarrollo. El repositorio es `https://github.com/olidepalma/GarminTrainingPlaner.git`. Si todavía no tienes el checkout, clónalo con `git clone https://github.com/olidepalma/GarminTrainingPlaner.git /opt/GarminTrainingPlaner` (el directorio de destino debe estar vacío). El entorno virtual debe crearse en Linux. Desde esa carpeta:

```sh
cd /opt/GarminTrainingPlaner
UV_PYTHON_INSTALL_DIR=/opt/gtp-python /opt/gtp-tools/bin/uv sync --locked --no-dev --python 3.12
chmod -R a+rX /opt/gtp-python
install -m 0640 deploy/environment.example /etc/garmin-planner/environment
install -m 0644 deploy/garmin-planner.service /etc/systemd/system/garmin-planner.service
```

Modifica `/etc/garmin-planner/environment`: dominio real en `GTP_PUBLIC_ORIGIN`, puerto, ruta de datos y proxy. El servicio lee este archivo; la app conserva el entorno de desarrollo local por defecto.

## Migrar los datos actuales

Detén la web en tu Mac/Windows antes de copiar **todo `data/`**. No copies una SQLite activa ni compartas tokens renovables entre dos servidores encendidos. El conjunto contiene base de datos, EPUB y versiones, conexiones Garmin/Pro y clave de cifrado. La clave y los `.enc` deben viajar juntos. Transfiere mediante SCP/SFTP por SSH, nunca dentro de Git. En Mac, desde el proyecto, con SSH ya preparado y sustituyendo el destino:

```sh
scp -r data/. usuario@IP_DEL_LXC:/ruta/privada/de/transferencia/
```

La carpeta de transferencia debe ser privada y creada previamente; si se usa root puede ser `/root/gtp-transfer`. En el LXC, detén el servicio si ya existe. Para una instalación inicial **con el directorio de destino vacío**:

```sh
cp -a /root/gtp-transfer/. /var/lib/garmin-planner/
chown -R garmin-planner:garmin-planner /var/lib/garmin-planner
chmod -R go-rwx /var/lib/garmin-planner
```

No mezcles dos bases de datos ni restaures encima de datos activos. Conserva el origen como respaldo hasta verificar. La contraseña del panel, sesiones deportivas, biblioteca y perfil se conservan. No hace falta volver a cargar el EPUB.

OpenAI requiere un identificador estable propio del servidor. Tras importar secretos, crea uno nuevo **una sola vez**, antes del primer arranque:

```sh
cd /opt/GarminTrainingPlaner
runuser -u garmin-planner -- .venv/bin/python -c 'import uuid; from pathlib import Path; from garmin_planner.storage import Vault; Vault(Path("/var/lib/garmin-planner")).write("host", {"id": "urn:uuid:" + str(uuid.uuid4())})'
```

Este paso no elimina la conexión importada. No lo repitas en actualizaciones o restauraciones del mismo LXC. Deja que el LXC gestione la renovación; si quieres continuar usando desarrollo local, autoriza una conexión separada allí. [Procedimiento oficial para servidores propios](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms).

## Arranque automático

```sh
systemctl daemon-reload
systemctl enable --now garmin-planner
systemctl status garmin-planner
journalctl -u garmin-planner -n 50 --no-pager
curl -fsS -H "Host: 127.0.0.1:8000" http://IP_DEL_LXC:8000/api/health
```

No uses `--reload` en producción. Reinicio: `systemctl restart garmin-planner`. Los datos persisten fuera del código. El sandbox de systemd permite escritura únicamente en el directorio de datos y su `/tmp` privado; el servicio no se ejecuta como root.

## Proxy, DNS y HTTPS

Con proxy en el mismo LXC, conserva `GTP_HOST=127.0.0.1`. Si ya tienes Nginx Proxy Manager no instales un segundo proxy. Hay ejemplos opcionales de Caddy y Nginx en `deploy/`. El certificado, DNS y rutas/firewall dependen de tu instalación. En Nginx Proxy Manager: destino HTTP a la IP del LXC y puerto 8000, certificado válido, Force SSL, Preserve Host y `X-Forwarded-Proto: https` hacia el backend.

Con proxy en otro LXC: `GTP_HOST=IP_LOCAL_FIJA_DEL_LXC`, añade la IP concreta del proxy a `GTP_TRUSTED_PROXY_IPS` junto a loopback, y limita el puerto 8000 en el firewall a ese proxy. Nunca redirijas ese puerto desde Internet. La URL pública exacta habilita Host y Origin; otras solicitudes y dominios se rechazan. Las cookies del dominio son Secure, HttpOnly y SameSite=Lax. La primera contraseña, si no migraste datos, se crea desde el túnel local antes de publicar el proxy.

## ChatGPT Pro y túnel local

La web del dominio permite generar, aceptar y consultar planes con la conexión del servidor. Para autorizar o reconectar Pro, el retorno oficial debe seguir siendo HTTP en `127.0.0.1` con ruta `/auth/callback`; no sustituir por el dominio HTTPS. [Registro y retorno oficiales](https://developers.openai.com/siwc/token-sharing-open-source/sign-in).

Detén tu servidor de desarrollo para liberar el puerto local. En Mac o PowerShell de Windows:

```sh
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8000:IP_DEL_LXC:8000 usuario@IP_DEL_LXC
```

Si la aplicación escucha en loopback, sustituye la segunda IP del túnel por `127.0.0.1`. Mantén el túnel abierto, entra en `http://127.0.0.1:8000`, inicia sesión con la contraseña del panel y conecta Pro. Completa la autorización en tu navegador y vuelve al dominio. El puerto local debe coincidir con `GTP_PORT`; no lo cambies únicamente en el túnel, porque rompería Origin y retorno OAuth. Cierra el túnel después de autorizar. No es necesario para las generaciones normales.

## Verificación y mantenimiento

Antes de dar por terminada la migración, comprueba acceso HTTPS, login y cierre de sesión, perfil, libro seleccionado, calendario y estadísticas. Haz una sincronización incremental de Garmin y una consulta de modelos Pro; la prueba de conexión consume un uso mínimo de Pro. Revisa la sincronización nocturna al día siguiente. No hace falta crear entrenamientos de prueba ni reenviar sesiones ya publicadas.

Para copias consistentes, detén brevemente el servicio y copia todo `/var/lib/garmin-planner`, incluyendo secretos y clave; arráncalo después. Protege las copias igual que los datos originales. Las copias de Proxmox deben incluir el volumen de datos; los bind mounts externos pueden necesitar respaldo independiente. Prueba una restauración sin arrancar simultáneamente la copia con las mismas conexiones.

Para actualizar: copia/actualiza el código, detén el servicio, realiza respaldo de los datos, ejecuta `uv sync --locked --no-dev --python 3.12` con el mismo `UV_PYTHON_INSTALL_DIR` y reinicia. Conserva la revisión anterior para volver atrás; una restauración de código no revierte automáticamente la base de datos. No guardes credenciales, backups o configuración privada en Git.

Este repositorio proporciona configuración y validaciones; la instalación real depende de los datos del LXC y del proxy. No se ha desplegado ni publicado automáticamente.

## Instalación y actualizaciones desde el repositorio

Con `uv` preparado, el checkout en `/opt/GarminTrainingPlaner` y como root:

```sh
bash deploy/install-lxc.sh
nano /etc/garmin-planner/environment
# Importar los datos antes de arrancar, como se explica arriba.
systemctl enable --now garmin-planner
```

El instalador conserva la configuración existente, crea el entorno de Linux, instala systemd y no publica ni arranca una configuración de ejemplo. El arranque al iniciar el LXC queda habilitado con `enable --now`.

Para próximas versiones, con un remoto Git configurado y el checkout limpio:

```sh
cd /opt/GarminTrainingPlaner
git pull --ff-only
bash deploy/update-lxc.sh
```

La actualización detiene la aplicación, respalda los datos de forma consistente, sincroniza dependencias e instala el servicio actualizado. Las copias contienen secretos y se guardan con permisos privados en `/var/backups/garmin-planner`. No se borran automáticamente. Si falla el respaldo o la instalación, el servicio queda detenido y se explica el error; no se presupone un rollback de base de datos. La receta usa `/var/lib/garmin-planner`: adapta el respaldo si personalizas esa ruta. Los scripts no crean contenedores ni modifican Nginx Proxy Manager.

Las IPs `192.168.1.50` y `192.168.1.10` de la plantilla son ejemplos: sustitúyelas por la IP fija de la web y la del proxy. El proceso escucha en esa IP de la LAN; el acceso del navegador se hace mediante el dominio HTTPS. El firewall del LXC debe permitir el backend solo desde Nginx Proxy Manager y desde el propio LXC para el túnel SSH.
