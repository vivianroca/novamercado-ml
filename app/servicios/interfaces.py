"""Puertos sustituibles: no implementan modelos ni almacenamiento."""

from typing import Any, Protocol

from app.schemas.respuestas import ResultadoPrediccion
from app.schemas.solicitudes import Calidad, SolicitudObservaciones, SolicitudPrediccion


class ServicioNoDisponible(RuntimeError):
    pass


class Predictor(Protocol):
    def predecir(self, solicitud: SolicitudPrediccion) -> ResultadoPrediccion:
        """Retorna una versión y un resultado por cada familia solicitada."""
        ...


class RegistroObservaciones(Protocol):
    def guardar(self, original: dict[str, Any], solicitud: SolicitudObservaciones,
                calidad: Calidad) -> int:
        """Retorna SOLO registros efectivamente nuevos/modificados tras confirmar guardado.

        Un reenvío idéntico debe retornar 0. Debe guardar original, canónico y
        calidad de forma atómica. Si no puede confirmar, lanza ServicioNoDisponible.
        """
        ...


class RegistroPredicciones(Protocol):
    def guardar_prediccion(self, original: dict[str, Any], solicitud: SolicitudPrediccion,
                           calidad: Calidad, resultado: ResultadoPrediccion):
        """Confirma solicitud, calidad y predicciones con versión en una transacción."""
        ...
