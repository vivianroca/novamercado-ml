"""Aplicación HTTP; los proveedores de ML y DB aún no están configurados."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.solicitudes import router
from app.calidad.normalizacion import SolicitudInvalida
from app.servicios.interfaces import ServicioNoDisponible


def crear_app() -> FastAPI:
    instancia = FastAPI(title="NovaMercado", docs_url=None, redoc_url=None, openapi_url=None)
    instancia.include_router(router)

    @instancia.exception_handler(SolicitudInvalida)
    async def solicitud_invalida(request, error):
        return JSONResponse(status_code=422, content={"detail": error.detail})

    @instancia.exception_handler(ServicioNoDisponible)
    async def servicio_no_disponible(request, error):
        return JSONResponse(status_code=503, content={"detail": str(error)})

    return instancia


app = crear_app()
