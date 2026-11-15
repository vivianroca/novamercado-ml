"""Configuración diferida y proveedores reemplazables con dependency_overrides."""

import os

from app.calidad.normalizacion import Catalogos
from app.servicios.interfaces import ServicioNoDisponible


def obtener_catalogos() -> Catalogos:
    try:
        return Catalogos.desde_directorio(os.environ.get("DATA_DIR", "data"))
    except (OSError, ValueError, KeyError) as error:
        raise ServicioNoDisponible("Catálogos no disponibles o inválidos") from error


def obtener_predictor():
    # Se devuelve un puerto no configurado para validar primero la solicitud.
    return PredictorNoConfigurado()


def obtener_registro():
    return RegistroNoConfigurado()


class PredictorNoConfigurado:
    def predecir(self, solicitud):
        raise ServicioNoDisponible("Modelo de predicción no configurado")


class RegistroNoConfigurado:
    def guardar(self, original, solicitud, calidad):
        raise ServicioNoDisponible("Almacenamiento de observaciones no configurado")
