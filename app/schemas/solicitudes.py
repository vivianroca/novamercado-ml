"""Contrato canónico: las conversiones pertenecen a app.calidad."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

EnteroNoNegativo = Annotated[StrictInt, Field(ge=0)]


class Contrato(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccionCalidad(Contrato):
    campo: StrictStr
    accion: Literal["reparar", "advertir"]
    detalle: StrictStr


class Calidad(Contrato):
    estado: Literal["ok", "corregido", "advertencia"]
    observaciones: list[AccionCalidad]


class FamiliaPrediccion(Contrato):
    familia_id: StrictStr
    en_promocion: EnteroNoNegativo


class VentaObservada(Contrato):
    familia_id: StrictStr
    ventas: EnteroNoNegativo


class SolicitudPrediccion(Contrato):
    tienda_id: Annotated[StrictInt, Field(gt=0)]
    fecha: date
    familias: Annotated[list[FamiliaPrediccion], Field(min_length=1)]


class SolicitudObservaciones(Contrato):
    tienda_id: Annotated[StrictInt, Field(gt=0)]
    fecha: date
    ventas: Annotated[list[VentaObservada], Field(min_length=1)]
