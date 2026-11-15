"""Sondas de solo lectura, con tiempos de espera y sin caché de salud."""
from concurrent.futures import ThreadPoolExecutor
import os

import httpx

from app.db.conexion import conectar_producto


class SondasDependencias:
    def __init__(self, conectar=conectar_producto, transporte=None):
        self.conectar = conectar
        self.transporte = transporte

    def db(self):
        with self.conectar() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute("SET statement_timeout = '3000ms'")
                cursor.execute("SELECT 1")
                if cursor.fetchone() != (1,):
                    raise ValueError("DB inválida")

    def _get(self, variable, ruta):
        base = os.environ.get(variable, "")
        if not base.startswith(("http://", "https://")):
            raise ValueError("Dependencia no configurada")
        with httpx.Client(timeout=3, transport=self.transporte, follow_redirects=False) as cliente:
            respuesta = cliente.get(base.rstrip("/") + ruta)
            respuesta.raise_for_status()
            return respuesta

    def mlflow(self):
        self._get("MLFLOW_TRACKING_URI", "/health")

    def airflow(self):
        valor = self._get("AIRFLOW_BASE_URL", "/api/v2/monitor/health").json()
        for componente in ("metadatabase", "scheduler", "dag_processor"):
            if valor.get(componente, {}).get("status") != "healthy":
                raise ValueError("Airflow no saludable")

    def comprobar(self):
        def ejecutar(nombre):
            try:
                getattr(self, nombre)()
                return None
            except Exception:
                return nombre
        with ThreadPoolExecutor(max_workers=3) as pool:
            return [nombre for nombre in pool.map(ejecutar, ("db", "mlflow", "airflow")) if nombre]
