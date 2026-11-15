"""Respuestas públicas del anexo y resultado del proveedor de predicciones."""

from datetime import date
from typing import Annotated

from pydantic import Field, StrictFloat, StrictInt, StrictStr

from app.schemas.solicitudes import Calidad, Contrato, EnteroNoNegativo


class PrediccionFamilia(Contrato):
    familia_id: StrictStr
    venta_esperada: Annotated[StrictFloat, Field(ge=0, allow_inf_nan=False)]
    cantidad_sugerida: EnteroNoNegativo


class ResultadoPrediccion(Contrato):
    version_modelo: Annotated[StrictStr, Field(min_length=1)]
    predicciones: Annotated[list[PrediccionFamilia], Field(min_length=1)]


class RespuestaPrediccion(ResultadoPrediccion):
    tienda_id: StrictInt
    fecha: date
    calidad: Calidad


class RespuestaObservaciones(Contrato):
    registros_guardados: EnteroNoNegativo
    calidad: Calidad
