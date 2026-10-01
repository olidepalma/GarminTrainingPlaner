#!/usr/bin/env bash
# Ejecutar después de git pull --ff-only en el LXC.
set -euo pipefail
umask 077
if [[ ${EUID} -ne 0 ]]; then
  echo 'Ejecuta la actualización como root dentro del LXC.' >&2
  exit 1
fi
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
if [[ "$project_root" != /opt/garmin-planner ]]; then
  echo 'El checkout debe estar en /opt/garmin-planner.' >&2
  exit 1
fi
uv_bin=${GTP_UV_BIN:-/opt/gtp-tools/bin/uv}
if [[ ! -x "$uv_bin" ]]; then echo 'No se encuentra uv.' >&2; exit 1; fi
# Esta receta usa la ruta fija del servicio; no guardar una copia vacía de otra ruta.
if ! grep -Eq '^GTP_DATA_DIR=/var/lib/garmin-planner$' /etc/garmin-planner/environment; then
  echo 'Ruta de datos personalizada: adapta el respaldo antes de actualizar.' >&2
  exit 1
fi
systemctl stop garmin-planner
install -d -m 0700 /var/backups/garmin-planner
backup_path="/var/backups/garmin-planner/data-$(date -u +%Y%m%dT%H%M%SZ)-$$.tar.gz"
if ! tar -czf "$backup_path" -C /var/lib/garmin-planner .; then
  echo 'El respaldo falló. Servicio detenido; resuelve la causa antes de continuar.' >&2
  exit 1
fi
cd "$project_root"
export UV_PYTHON_INSTALL_DIR=/opt/gtp-python
if ! "$uv_bin" sync --locked --no-dev --python 3.12; then
  echo 'Actualización fallida. Servicio detenido; conserva el respaldo y revisa dependencias.' >&2
  exit 1
fi
if [[ -d /opt/gtp-python ]]; then chmod -R a+rX /opt/gtp-python; fi
install -m 0644 deploy/garmin-planner.service /etc/systemd/system/garmin-planner.service
systemctl daemon-reload
systemctl start garmin-planner
systemctl --no-pager status garmin-planner
echo "Respaldo privado: $backup_path"
