"""Estado operativo y modelo efectivamente cargado."""
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictStr

from app.api.dependencias import obtener_predictor
from app.servicios.interfaces import ServicioNoDisponible
from app.servicios.salud import SondasDependencias

router = APIRouter()


def obtener_sondas():
    return SondasDependencias()


class ModeloVigente(BaseModel):
    nombre: StrictStr
    alias: StrictStr
    version: StrictStr


@router.get("/modelo", response_model=ModeloVigente)
def modelo(predictor: Annotated[object, Depends(obtener_predictor)]):
    predictor.cache.iniciar()
    snapshot = predictor.cache.actual
    if snapshot is None:
        raise ServicioNoDisponible("No hay modelo champion cargado")
    return ModeloVigente(nombre=predictor.cache.fuente.nombre,
                        alias=predictor.cache.fuente.alias, version=snapshot.version)


@router.get("/health")
def health(predictor: Annotated[object, Depends(obtener_predictor)],
           sondas: Annotated[object, Depends(obtener_sondas)]):
    predictor.cache.iniciar()
    if predictor.cache.actual is None:
        return JSONResponse(status_code=503, content={"estado": "degradado", "motivo": "No hay modelo champion cargado"})
    fallos = sondas.comprobar()
    if predictor.cache.ultimo_error:
        fallos.append("actualización del champion")
    if fallos:
        return {"estado": "degradado", "motivo": "Dependencias no disponibles: " + ", ".join(fallos)}
    return {"estado": "ok"}
