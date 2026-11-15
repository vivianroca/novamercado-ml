"""Configuración diferida y proveedores reemplazables con dependency_overrides."""

import os
from fastapi import Request

from app.calidad.normalizacion import Catalogos
from app.db.repositorio import RepositorioProducto
from app.servicios.interfaces import ServicioNoDisponible
from app.servicios.interfaces import RegistroObservaciones, RegistroPredicciones


def obtener_catalogos() -> Catalogos:
    try:
        return Catalogos.desde_directorio(os.environ.get("DATA_DIR", "data"))
    except (OSError, ValueError, KeyError) as error:
        raise ServicioNoDisponible("Catálogos no disponibles o inválidos") from error


def obtener_predictor(request: Request):
    # Singleton por aplicación, sin IO hasta recibir una solicitud válida.
    with request.app.state.predictor_lock:
        if request.app.state.predictor is None:
            from app.servicios.prediccion import CacheChampion, FuenteMLflow, PredictorChampion, VariablesPrediccion
            variables = VariablesPrediccion(os.environ.get("DATA_DIR", "data"), RepositorioProducto())
            fuente = FuenteMLflow(os.environ.get("MLFLOW_TRACKING_URI"),
                os.environ.get("MODEL_NAME", "novamercado-histgradientboosting"), "champion",
                os.environ.get("MODEL_CACHE_DIR", "models"), variables.validar_metadata)
            cache = CacheChampion(fuente, float(os.environ.get("MODEL_REFRESH_SECONDS", "30")))
            request.app.state.predictor = PredictorChampion(cache, variables)
        return request.app.state.predictor


def obtener_registro() -> RegistroObservaciones:
    return RepositorioProducto()


def obtener_registro_predicciones() -> RegistroPredicciones:
    return RepositorioProducto()


def obtener_reentrenamientos():
    from app.servicios.reentrenamientos import ClienteReentrenamientos
    return ClienteReentrenamientos(os.environ.get("AIRFLOW_BASE_URL"),
        os.environ.get("AIRFLOW_USER") or os.environ.get("AIRFLOW_ADMIN_USER"),
        os.environ.get("AIRFLOW_PASSWORD") or os.environ.get("AIRFLOW_ADMIN_PASSWORD"))
