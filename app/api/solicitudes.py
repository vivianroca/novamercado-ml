"""Adaptadores HTTP; la limpieza permanece en app.calidad."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends
from pydantic import ValidationError

from app.api.dependencias import obtener_catalogos, obtener_predictor, obtener_registro, obtener_registro_predicciones
from app.calidad.normalizacion import Catalogos, normalizar_observaciones, normalizar_prediccion
from app.schemas.respuestas import RespuestaObservaciones, RespuestaPrediccion, ResultadoPrediccion
from app.servicios.interfaces import Predictor, RegistroObservaciones, RegistroPredicciones, ServicioNoDisponible

router = APIRouter(prefix="/v1")


@router.post("/prediccion", response_model=RespuestaPrediccion, status_code=200)
def predecir(
    entrada: Annotated[Any, Body()],
    catalogos: Annotated[Catalogos, Depends(obtener_catalogos)],
    predictor: Annotated[Predictor, Depends(obtener_predictor)],
    registro: Annotated[RegistroPredicciones, Depends(obtener_registro_predicciones)],
):
    solicitud, calidad = normalizar_prediccion(entrada, catalogos)
    try:
        resultado = ResultadoPrediccion.model_validate(predictor.predecir(solicitud))
    except ValidationError as error:
        raise ServicioNoDisponible("El proveedor devolvió una predicción inválida") from error
    esperadas = {f.familia_id for f in solicitud.familias}
    recibidas = [p.familia_id for p in resultado.predicciones]
    if set(recibidas) != esperadas or len(recibidas) != len(esperadas):
        raise ServicioNoDisponible("El proveedor no devolvió exactamente las familias solicitadas")
    respuesta = RespuestaPrediccion(
        tienda_id=solicitud.tienda_id, fecha=solicitud.fecha, calidad=calidad,
        **resultado.model_dump(),
    )
    registro.guardar_prediccion(entrada, solicitud, calidad, resultado)
    return respuesta


@router.post("/observaciones", response_model=RespuestaObservaciones, status_code=200)
def observar(
    entrada: Annotated[Any, Body()],
    catalogos: Annotated[Catalogos, Depends(obtener_catalogos)],
    registro: Annotated[RegistroObservaciones, Depends(obtener_registro)],
):
    solicitud, calidad = normalizar_observaciones(entrada, catalogos)
    guardados = registro.guardar(entrada, solicitud, calidad)
    if type(guardados) is not int or not 0 <= guardados <= len(solicitud.ventas):
        raise ServicioNoDisponible("El proveedor no confirmó un conteo válido de registros")
    return RespuestaObservaciones(registros_guardados=guardados, calidad=calidad)
