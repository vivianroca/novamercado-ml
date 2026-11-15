"""Inicialización explícita y transaccional: python -m app.db.migrar."""

from pathlib import Path

from app.db.conexion import conectar_producto


def aplicar_esquema(conectar=conectar_producto):
    with conectar() as conexion:
        # Serializa inicializadores concurrentes de esta misma aplicación.
        conexion.execute("SELECT pg_advisory_xact_lock(308031)")
        conexion.execute(Path(__file__).with_name("esquema.sql").read_text())


if __name__ == "__main__":
    aplicar_esquema()
