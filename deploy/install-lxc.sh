#!/usr/bin/env bash
# Ejecutar como root desde el checkout definitivo (/opt/GarminTrainingPlaner).
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then
  echo 'Ejecuta este instalador como root dentro del LXC.' >&2
  exit 1
fi
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
if [[ "$project_root" != /opt/GarminTrainingPlaner ]]; then
  echo 'Coloca el checkout en /opt/GarminTrainingPlaner antes de instalar.' >&2
  exit 1
fi
uv_bin=${GTP_UV_BIN:-/opt/gtp-tools/bin/uv}
if [[ ! -x "$uv_bin" ]]; then
  echo 'Instala uv según docs/LXC.md o indica su ruta mediante GTP_UV_BIN.' >&2
  exit 1
fi
if ! id garmin-planner >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/garmin-planner --create-home --shell /usr/sbin/nologin garmin-planner
fi
install -d -m 0700 -o garmin-planner -g garmin-planner /var/lib/garmin-planner
install -d -m 0750 /etc/garmin-planner
cd "$project_root"
export UV_PYTHON_INSTALL_DIR=/opt/gtp-python
"$uv_bin" sync --locked --no-dev --python 3.12
if [[ -d /opt/gtp-python ]]; then chmod -R a+rX /opt/gtp-python; fi
if [[ ! -e /etc/garmin-planner/environment ]]; then
  install -m 0640 deploy/environment.example /etc/garmin-planner/environment
fi
install -m 0644 deploy/garmin-planner.service /etc/systemd/system/garmin-planner.service
systemctl daemon-reload
echo 'Instalación preparada. Ajusta /etc/garmin-planner/environment y migra los datos.'
echo 'Después: systemctl enable --now garmin-planner'
