from datetime import date, timedelta
from types import SimpleNamespace

import joblib
import numpy as np
import pandas as pd
import pytest

from ml.baseline import Costos, Venta
from ml.features import Contexto, FeaturesCausales, NOMBRES
from ml.histgradient import ajuste_cuantil, evaluar_histgradient
from ml.modelo_inventario import InventarioHGB

D = date(2026, 1, 5)


@pytest.fixture
def contexto():
    return Contexto(
        {1: {"ciudad": "Guatemala", "tipo": "express", "fecha_apertura": "2024-01-01"},
         2: {"ciudad": "Cobán", "tipo": "express", "fecha_apertura": "2024-01-01"}},
        {"pan": 0}, {"Guatemala": 0, "Cobán": 1}, {"express": 0},
        {(D, "nacional"): {"pago"}, (D, "Guatemala"): {"feriado"}})


def test_features_no_usan_dia_actual_ni_futuro(contexto):
    engine = FeaturesCausales(contexto)
    engine.agregar([Venta(D - timedelta(days=d), 1, "pan", d) for d in range(1, 57)])
    antes = engine.fila(1, "pan", D, 3)
    engine.agregar([Venta(D, 1, "pan", 9999), Venta(D + timedelta(days=1), 1, "pan", 10000)])
    np.testing.assert_equal(engine.fila(1, "pan", D, 3), antes)
    f = dict(zip(NOMBRES, antes))
    assert f["lag_1"] == 1 and f["lag_7"] == 7 and f["lag_28"] == 28
    assert f["media_7"] == 4 and f["conteo_56"] == 56
    assert f["en_promocion"] == 3


def test_feriado_local_aplica_solo_a_su_ciudad(contexto):
    engine = FeaturesCausales(contexto)
    guatemala = dict(zip(NOMBRES, engine.fila(1, "pan", D, 0)))
    coban = dict(zip(NOMBRES, engine.fila(2, "pan", D, 0)))
    assert guatemala["local_feriado"] == 1 and coban["local_feriado"] == 0
    assert guatemala["nacional_pago"] == coban["nacional_pago"] == 1


def test_sin_historial_no_imputa_ventas_cero(contexto):
    f = dict(zip(NOMBRES, FeaturesCausales(contexto).fila(1, "pan", D, 0)))
    assert np.isnan(f["lag_1"]) and np.isnan(f["media_7"])
    assert f["conteo_7"] == 0


def test_features_no_mezclan_tiendas_y_rechazan_duplicados(contexto):
    engine = FeaturesCausales(contexto)
    venta = Venta(D - timedelta(days=1), 2, "pan", 100)
    engine.agregar([venta])
    assert np.isnan(dict(zip(NOMBRES, engine.fila(1, "pan", D, 0)))["lag_1"])
    with pytest.raises(ValueError, match="duplicada"):
        engine.agregar([venta])


@pytest.mark.parametrize("promocion", [True, -1, 0.5, None])
def test_promocion_invalida(contexto, promocion):
    with pytest.raises(ValueError):
        FeaturesCausales(contexto).fila(1, "pan", D, promocion)


def test_cuantil_residual_depende_de_costos():
    residuos = [-5, -2, 0, 2, 5]
    assert ajuste_cuantil(residuos, Costos(10, 1)) == 5
    assert ajuste_cuantil(residuos, Costos(1, 10)) == -5


@pytest.fixture
def datos(contexto):
    engine = FeaturesCausales(contexto)
    x, ventas = [], []
    for dia in range(100):
        f = D - timedelta(days=90) + timedelta(days=dia)
        v = Venta(f, 1, "pan", 10 + dia % 7)
        x.append(engine.fila(1, "pan", f, dia % 3))
        ventas.append(v)
        engine.agregar([v])
    return np.array(x), ventas


def test_validacion_no_ajusta_pesos_ni_calibracion(datos):
    x, ventas = datos
    costos = {"pan": Costos(1, 2)}
    parametros = {"max_iter": 5, "min_samples_leaf": 2}
    modelo, reporte, filas = evaluar_histgradient(x, ventas, costos, D, D + timedelta(days=9), parametros=parametros)
    alteradas = [Venta(v.fecha, v.tienda_id, v.familia_id, 10000 if v.fecha >= D else v.ventas) for v in ventas]
    otro, r2, _ = evaluar_histgradient(x, alteradas, costos, D, D + timedelta(days=9), parametros=parametros)
    assert reporte["ajuste_hasta"] < reporte["calibracion_inicio"]
    assert reporte["calibracion_fin"] < reporte["inicio"]
    assert reporte["filas_validacion"] == reporte["baseline"]["metricas"]["registros"] == 10
    assert reporte["ajustes_por_familia"] == r2["ajustes_por_familia"]
    assert modelo.get_params()["early_stopping"] is False
    from threadpoolctl import threadpool_limits
    with threadpool_limits(limits=2):
        np.testing.assert_allclose(modelo.predict(x), otro.predict(x))
    assert all(f["cantidad_sugerida"] >= 0 and type(f["cantidad_sugerida"]) is int for f in filas)


def test_modelo_serializable_incluye_sugerido(datos, tmp_path):
    x, ventas = datos
    modelo, reporte, filas = evaluar_histgradient(x, ventas, {"pan": Costos(1, 2)}, D, D + timedelta(days=9),
                                                  parametros={"max_iter": 5, "min_samples_leaf": 2})
    ruta = tmp_path / "modelo.joblib"
    joblib.dump({"estimador": modelo, "features": NOMBRES, "ajustes_codificados": {0: reporte["ajustes_por_familia"]["pan"]}}, ruta)
    envuelto = InventarioHGB()
    envuelto.load_context(SimpleNamespace(artifacts={"bundle": str(ruta)}))
    salida = envuelto.predict(None, pd.DataFrame(x[-10:], columns=NOMBRES))
    np.testing.assert_allclose(salida.venta_esperada, [f["venta_esperada"] for f in filas])
    assert salida.cantidad_sugerida.tolist() == [f["cantidad_sugerida"] for f in filas]


def test_rechaza_early_stopping_aleatorio(datos):
    with pytest.raises(ValueError, match="aleatoria"):
        evaluar_histgradient(*datos, {"pan": Costos(1, 2)}, D, D, parametros={"early_stopping": True})
