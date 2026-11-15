from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from types import SimpleNamespace
import threading

import numpy as np
import pandas as pd
import pytest

from app.calidad.normalizacion import SolicitudInvalida
from app.schemas.solicitudes import SolicitudPrediccion
from app.servicios.interfaces import ServicioNoDisponible
from app.servicios.prediccion import CacheChampion, ModeloCargado, PredictorChampion, VariablesPrediccion
from ml.baseline import Venta
from ml.features import NOMBRES


class Fuente:
    def __init__(self):
        self.version = "1"
        self.consultas = 0
        self.cargas = 0
        self.caida = False
        self.invalido = False

    def consultar(self):
        self.consultas += 1
        if self.caida:
            raise ConnectionError("MLflow apagado")
        return SimpleNamespace(version=self.version)

    def cargar(self, version):
        self.cargas += 1
        if self.invalido:
            raise ValueError("Artefacto corrupto")
        return ModeloCargado(object(), version.version, date(2026, 1, 3), {})


def test_cache_no_consulta_por_cada_prediccion_y_sobrevive_caida():
    fuente = Fuente()
    cache = CacheChampion(fuente)
    try:
        primero = cache.obtener()
        for _ in range(4):
            assert cache.obtener() is primero
        assert fuente.consultas == fuente.cargas == 1
        fuente.caida = True
        cache.refrescar()
        assert cache.obtener() is primero and cache.ultimo_error == "ConnectionError"
        fuente.caida = False
        fuente.version = "2"
        cache.refrescar()
        assert cache.obtener().version == "2" and cache.ultimo_error is None
    finally:
        cache.cerrar()


def test_modelo_nuevo_invalido_no_desplaza_cargado():
    fuente = Fuente()
    cache = CacheChampion(fuente)
    try:
        primero = cache.obtener()
        fuente.version, fuente.invalido = "2", True
        cache.refrescar()
        assert cache.obtener() is primero and cache.obtener().version == "1"
    finally:
        cache.cerrar()


def test_sin_modelo_ni_mlflow_rechaza_sin_inventar():
    fuente = Fuente()
    fuente.caida = True
    with pytest.raises(ServicioNoDisponible, match="No hay modelo champion"):
        CacheChampion(fuente).obtener()


def test_refresco_bloqueado_no_bloquea_modelo_cargado():
    fuente = Fuente()
    cache = CacheChampion(fuente)
    listo, liberar = threading.Event(), threading.Event()
    try:
        primero = cache.obtener()
        original = fuente.consultar
        def lento():
            listo.set()
            assert liberar.wait(timeout=3)
            return original()
        fuente.consultar = lento
        with ThreadPoolExecutor(max_workers=2) as pool:
            refresco = pool.submit(cache.refrescar)
            assert listo.wait(timeout=1)
            try:
                assert pool.submit(cache.obtener).result(timeout=1) is primero
            finally:
                liberar.set()
            refresco.result(timeout=2)
    finally:
        liberar.set()
        cache.cerrar()


def test_version_corresponde_al_snapshot_usado():
    cache = SimpleNamespace()
    class Modelo:
        def predict(self, x):
            cache.actual = ModeloCargado(self, "2", date(2026, 1, 3), {})
            return pd.DataFrame({"venta_esperada": [12.5], "cantidad_sugerida": [15]})
    cache.actual = ModeloCargado(Modelo(), "1", date(2026, 1, 3), {})
    cache.obtener = lambda: cache.actual
    variables = SimpleNamespace(matriz=lambda *args: pd.DataFrame())
    solicitud = SolicitudPrediccion(tienda_id=5, fecha=date(2026, 3, 1), familias=[{"familia_id": "pan", "en_promocion": 0}])
    assert PredictorChampion(cache, variables).predecir(solicitud).version_modelo == "1"
    assert cache.actual.version == "2"


@pytest.mark.parametrize("venta,sugerido", [(float("nan"), 1), (1.0, -1), (-1.0, 0), (1.0, 1.5), (1.0, True)])
def test_modelo_invalido_no_se_convierte_en_prediccion(venta, sugerido):
    modelo = SimpleNamespace(predict=lambda x: pd.DataFrame({"venta_esperada": [venta], "cantidad_sugerida": [sugerido]}))
    cache = SimpleNamespace(obtener=lambda: ModeloCargado(modelo, "1", date(2026, 1, 3), {}))
    variables = SimpleNamespace(matriz=lambda *args: pd.DataFrame())
    solicitud = SolicitudPrediccion(tienda_id=5, fecha=date(2026, 3, 1), familias=[{"familia_id": "pan", "en_promocion": 0}])
    with pytest.raises(ServicioNoDisponible):
        PredictorChampion(cache, variables).predecir(solicitud)


def test_variables_reconcilian_pasado_sin_usar_observaciones_actuales(modelo_serving):
    fecha = date(2026, 1, 9)  # D-1 ya existe en CSV: PostgreSQL debe prevalecer.
    repo = SimpleNamespace(leer_observaciones=lambda *args: [
        Venta(fecha - timedelta(days=1), 5, "pan", 123),
        Venta(fecha, 5, "pan", 99999), Venta(fecha + timedelta(days=1), 5, "pan", 99999)])
    variables = VariablesPrediccion(modelo_serving.data_dir, repo)
    snapshot = ModeloCargado(None, "1", date(2026, 1, 3), modelo_serving.metadata)
    solicitud = SolicitudPrediccion(tienda_id=5, fecha=fecha, familias=[{"familia_id": "pan", "en_promocion": 3}])
    x = variables.matriz(solicitud, snapshot)
    assert x.loc[0, "lag_1"] == 123 and x.loc[0, "en_promocion"] == 3
    assert x.loc[0, "media_7"] < 1000
    assert list(x.columns) == NOMBRES
    solicitud.fecha = snapshot.corte
    with pytest.raises(SolicitudInvalida, match="corte"):
        variables.matriz(solicitud, snapshot)
