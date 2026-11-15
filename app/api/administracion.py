"""Endpoints administrativos: contrato del PDF, sin lógica de entrenamiento."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.dependencias import obtener_reentrenamientos
from app.calidad.normalizacion import SolicitudInvalida
from app.schemas.administracion import EstadoReentrenamiento, InicioReentrenamiento
from app.servicios.reentrenamientos import ClienteReentrenamientos, EjecucionDesconocida

router = APIRouter(prefix="/admin")


async def sin_cuerpo(request: Request):
    if await request.body():
        raise SolicitudInvalida("solicitud", "POST /admin/reentrenar no lleva cuerpo")


@router.post("/reentrenar", status_code=202, response_model=InicioReentrenamiento,
             dependencies=[Depends(sin_cuerpo)])
def iniciar(servicio: Annotated[ClienteReentrenamientos, Depends(obtener_reentrenamientos)]):
    return servicio.iniciar()


@router.get("/reentrenar/{id}", response_model=EstadoReentrenamiento, response_model_exclude_none=True)
def consultar(id: str, servicio: Annotated[ClienteReentrenamientos, Depends(obtener_reentrenamientos)]):
    try:
        return servicio.consultar(id)
    except EjecucionDesconocida as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
