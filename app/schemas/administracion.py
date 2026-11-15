"""Contrato administrativo del anexo."""

from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictStr, model_validator

from app.schemas.solicitudes import Contrato

Texto = Annotated[StrictStr, Field(min_length=1)]


class InicioReentrenamiento(Contrato):
    id: Texto


class EstadoReentrenamiento(Contrato):
    estado: Literal["en_curso", "exitoso", "fallido"]
    promovido: StrictBool | None = None
    version: Texto | None = None
    motivo: Texto | None = None

    @model_validator(mode="after")
    def campos_terminales(self):
        if self.estado != "en_curso" and any(v is None for v in (self.promovido, self.version, self.motivo)):
            raise ValueError("Un estado terminal requiere promovido, version vigente y motivo")
        return self
