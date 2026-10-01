"""Comandos portables: python -m garmin_planner doctor | serve."""

import argparse
import json
import platform
from importlib.metadata import PackageNotFoundError, version

import uvicorn

from garmin_planner.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Garmin Training Planner: entorno local")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser(
        "doctor", help="Comprueba configuración y dependencias sin conectar cuentas"
    )
    serve = subcommands.add_parser("serve", help="Inicia el servidor local")
    serve.add_argument("--reload", action="store_true", help="Recarga al editar código")
    args = parser.parse_args()
    settings = Settings()

    if args.command == "doctor":
        dependencies = {}
        for package in ("fastapi", "pydantic-settings", "uvicorn", "tzdata", "garminconnect"):
            try:
                dependencies[package] = version(package)
            except PackageNotFoundError:
                dependencies[package] = "no instalado (opcional)"
        print(
            json.dumps(
                {
                    "python": platform.python_version(),
                    "platform": platform.system(),
                    "timezone": settings.timezone,
                    "coach_provider": settings.coach_provider,
                    "dependencies": dependencies,
                    "garmin_connected": False,
                    "chatgpt_connected": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    uvicorn.run(
        "garmin_planner.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=args.reload,
        reload_dirs=["src/garmin_planner"] if args.reload else None,
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips=settings.trusted_proxy_ips,
    )


if __name__ == "__main__":
    main()
