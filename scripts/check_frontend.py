"""Comprueba sintaxis de módulos con Node; herramienta de desarrollo, no del servidor."""

import shutil
import subprocess
import sys
from pathlib import Path


def main():
    node = shutil.which("node")
    if not node:
        print(
            "Instala Node.js para comprobar la interfaz; el servidor no lo necesita.",
            file=sys.stderr,
        )
        return 1
    static = Path(__file__).resolve().parents[1] / "src" / "garmin_planner" / "static"
    for source in sorted(static.rglob("*.js")):
        result = subprocess.run(
            [node, "--check", "--input-type=module"],
            input=source.read_text(encoding="utf-8"),
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            print(f"{source.name}: {result.stderr}", file=sys.stderr)
            return 1
    print("Sintaxis de todos los módulos JavaScript comprobada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
