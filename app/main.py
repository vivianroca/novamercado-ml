"""Aplicación HTTP con PostgreSQL del producto y champion MLflow cargado en memoria."""

from contextlib import asynccontextmanager
import threading

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.solicitudes import router
from app.calidad.normalizacion import SolicitudInvalida
from app.servicios.interfaces import ServicioNoDisponible


def crear_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if app.state.predictor is not None:
                app.state.predictor.cerrar()

    instancia = FastAPI(title="NovaMercado", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    instancia.state.predictor_lock = threading.Lock()
    instancia.state.predictor = None
    instancia.include_router(router)

    @instancia.exception_handler(SolicitudInvalida)
    async def solicitud_invalida(request, error):
        return JSONResponse(status_code=422, content={"detail": error.detail})

    @instancia.exception_handler(ServicioNoDisponible)
    async def servicio_no_disponible(request, error):
        return JSONResponse(status_code=503, content={"detail": str(error)})

    return instancia


app = crear_app()
