"""Credenciales SimpleAuth de Airflow 3 desde entorno; nunca dentro de la imagen."""

import json
import os
from pathlib import Path

if __name__ == "__main__":
    destino = Path(os.environ["AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_PASSWORDS_FILE"])
    destino.parent.mkdir(parents=True, exist_ok=True)
    # Mantener credenciales existentes al reiniciar; no imprimir secretos.
    if not destino.exists():
        with destino.open("x") as archivo:
            json.dump({os.environ["AIRFLOW_ADMIN_USER"]: os.environ["AIRFLOW_ADMIN_PASSWORD"]}, archivo)
        destino.chmod(0o600)
