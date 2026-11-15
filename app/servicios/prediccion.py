"""Serving del champion: lectura MLflow, snapshot en memoria y features causales."""

from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import json
import logging
from numbers import Real
from pathlib import Path
import threading

import numpy as np
import pandas as pd

from app.calidad.normalizacion import SolicitudInvalida
from app.schemas.respuestas import ResultadoPrediccion
from app.servicios.interfaces import ServicioNoDisponible
from ml.datos import cargar_datos
from ml.features import Contexto, FeaturesCausales, NOMBRES

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModeloCargado:
    modelo: object
    version: str
    corte: date
    metadata: dict


class VariablesPrediccion:
    def __init__(self, data_dir, repositorio):
        self.data_dir = data_dir
        self.repositorio = repositorio
        self._contexto = None
        self._historico = {}
        self._lock = threading.Lock()

    def _cargar(self):
        with self._lock:
            if self._contexto is not None:
                return
            try:
                contexto = Contexto.cargar(self.data_dir)
                historial, _ = cargar_datos(self.data_dir)
                indice = {}
                for v in historial:
                    indice.setdefault((v.tienda_id, v.familia_id), {})[v.fecha] = v.ventas
            except (OSError, ValueError, KeyError) as error:
                raise ServicioNoDisponible("Insumos locales de predicción inválidos o ausentes") from error
            self._historico = indice
            self._contexto = contexto

    def validar_metadata(self, metadata):
        self._cargar()
        c = self._contexto
        esperados = {"features": NOMBRES, "familias": c.familias, "tiendas": sorted(c.tiendas),
                     "ciudades": c.ciudades, "formatos": c.formatos}
        if any(metadata.get(k) != v for k, v in esperados.items()):
            raise ValueError("Variables/códigos del modelo incompatibles con los catálogos locales")

    def matriz(self, solicitud, snapshot):
        self.validar_metadata(snapshot.metadata)
        if solicitud.fecha <= snapshot.corte:
            raise SolicitudInvalida("fecha", f"Debe ser posterior al corte de entrenamiento/calibración {snapshot.corte}")
        apertura = date.fromisoformat(self._contexto.tiendas[solicitud.tienda_id]["fecha_apertura"])
        if solicitud.fecha < apertura:
            raise SolicitudInvalida("fecha", "Fecha anterior a apertura de tienda")
        desde = solicitud.fecha - timedelta(days=56)
        familias = [f.familia_id for f in solicitud.familias]
        engine = FeaturesCausales(self._contexto)
        for familia in familias:
            engine.historial[(solicitud.tienda_id, familia)] = {
                f: v for f, v in self._historico.get((solicitud.tienda_id, familia), {}).items()
                if desde <= f < solicitud.fecha}
        observaciones = self.repositorio.leer_observaciones(solicitud.tienda_id, desde, solicitud.fecha, familias)
        for v in observaciones:
            # Defensa adicional incluso ante un proveedor sustituido incorrecto.
            if v.tienda_id == solicitud.tienda_id and v.familia_id in familias and desde <= v.fecha < solicitud.fecha:
                engine.historial[(v.tienda_id, v.familia_id)][v.fecha] = v.ventas
        filas = [engine.fila(solicitud.tienda_id, f.familia_id, solicitud.fecha, f.en_promocion)
                 for f in solicitud.familias]
        return pd.DataFrame(filas, columns=NOMBRES, dtype=float)


class FuenteMLflow:
    """Solo operaciones de lectura. URIs explícitos, sin modificar estado global."""

    def __init__(self, tracking_uri, nombre, alias, cache_dir, validar_metadata):
        self.tracking_uri = tracking_uri
        self.nombre = nombre
        self.alias = alias
        self.cache_dir = Path(cache_dir)
        self.validar_metadata = validar_metadata

    def _cliente(self):
        if not self.tracking_uri or not self.tracking_uri.startswith(("http://", "https://")):
            raise ServicioNoDisponible("Configurar URI HTTP de MLflow")
        from mlflow import MlflowClient
        return MlflowClient(tracking_uri=self.tracking_uri, registry_uri=self.tracking_uri)

    def consultar(self):
        version = self._cliente().get_model_version_by_alias(self.nombre, self.alias)
        if version.status != "READY":
            raise ValueError("Champion no está READY")
        return version

    def cargar(self, version):
        from mlflow.artifacts import download_artifacts
        from mlflow.pyfunc import load_model
        if not str(version.version).isdigit():
            raise ValueError("Versión de Registry inválida")
        destino = self.cache_dir / hashlib.sha256(self.nombre.encode()).hexdigest()[:16] / str(version.version)
        destino.mkdir(parents=True, exist_ok=True)
        cliente = self._cliente()
        metadata = json.loads(Path(cliente.download_artifacts(
            version.run_id, "configuracion/features_y_sugeridos.json", str(destino))).read_text())
        reporte = json.loads(Path(cliente.download_artifacts(
            version.run_id, "evaluacion/comparacion.json", str(destino))).read_text())
        corte = date.fromisoformat(reporte["calibracion_fin"])
        if not date.fromisoformat(reporte["ajuste_hasta"]) < date.fromisoformat(reporte["calibracion_inicio"]) <= corte:
            raise ValueError("Cortes del modelo inválidos")
        self.validar_metadata(metadata)
        # Fijar versión antes de descargar: no resolver champion dos veces.
        ruta = download_artifacts(artifact_uri=f"models:/{self.nombre}/{version.version}",
            tracking_uri=self.tracking_uri, registry_uri=self.tracking_uri, dst_path=str(destino))
        modelo = load_model(ruta, suppress_warnings=True)
        return ModeloCargado(modelo, str(version.version), corte, metadata)


class CacheChampion:
    def __init__(self, fuente, intervalo=30):
        if not np.isfinite(intervalo) or not 0 < intervalo <= 30:
            raise ValueError("Intervalo de refresco debe estar entre 0 y 30 segundos")
        self.fuente = fuente
        self.intervalo = intervalo
        self._actual = None
        self.ultimo_error = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def refrescar(self):
        with self._lock:
            try:
                version = self.fuente.consultar()
                if self._actual is None or str(version.version) != self._actual.version:
                    nuevo = self.fuente.cargar(version)
                    self._actual = nuevo  # Intercambio atómico solo después de carga completa.
                self.ultimo_error = None
            except Exception as error:
                self.ultimo_error = type(error).__name__
                logger.warning("Refresco champion falló (%s); se conserva el modelo cargado", self.ultimo_error)
        return self._actual

    @property
    def actual(self):
        return self._actual

    def _refresco_periodico(self):
        if self._actual is None:
            self.refrescar()
        while not self._stop.wait(self.intervalo):
            self.refrescar()

    def iniciar(self):
        """Arranque no bloqueante, incluso sin modelo o con Registry caído."""
        if self._thread is not None:
            return
        with self._lock:
            if self._thread is None and not self._stop.is_set():
                self._thread = threading.Thread(target=self._refresco_periodico, daemon=True, name="champion-refresh")
                self._thread.start()

    def obtener(self):
        if self._actual is None:
            self.refrescar()
        if self._actual is None:
            self.iniciar()
            raise ServicioNoDisponible("No hay modelo champion cargado")
        self.iniciar()
        return self._actual

    def cerrar(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)


class PredictorChampion:
    def __init__(self, cache, variables):
        self.cache = cache
        self.variables = variables

    def predecir(self, solicitud):
        snapshot = self.cache.obtener()
        x = self.variables.matriz(solicitud, snapshot)
        try:
            salida = snapshot.modelo.predict(x)
            if len(salida) != len(solicitud.familias):
                raise ValueError("Conteo de predicciones incorrecto")
            predicciones = []
            for familia, (_, fila) in zip(solicitud.familias, salida.iterrows()):
                venta, sugerido = fila["venta_esperada"], fila["cantidad_sugerida"]
                if any(isinstance(v, (bool, np.bool_)) or not isinstance(v, Real) or not np.isfinite(v) for v in (venta, sugerido)):
                    raise ValueError("Predicciones no numéricas o no finitas")
                if venta < 0 or sugerido < 0 or sugerido != int(sugerido):
                    raise ValueError("Predicciones negativas o sugerido no entero")
                predicciones.append({"familia_id": familia.familia_id,
                    "venta_esperada": float(venta), "cantidad_sugerida": int(sugerido)})
            return ResultadoPrediccion(version_modelo=snapshot.version, predicciones=predicciones)
        except Exception as error:
            raise ServicioNoDisponible("El modelo cargado no produjo una predicción válida") from error

    def cerrar(self):
        self.cache.cerrar()
