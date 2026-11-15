from datetime import date, timedelta

import pytest

from ml.baseline import BaselineSemanal, Costos, Venta, cantidad_optima, costo_negocio
from ml.datos import cargar_datos
from ml.evaluacion import evaluar_temporal, metricas


D = date(2026, 1, 5)


def venta(dias, unidades, tienda=1, familia="pan"):
    return Venta(D + timedelta(days=dias), tienda, familia, unidades)


def test_media_semanal_por_tienda_y_familia():
    modelo = BaselineSemanal([venta(-14, 10), venta(-7, 30), venta(-1, 1000),
                              venta(-7, 999, tienda=2), venta(-7, 500, familia="otra")],
                             {"pan": Costos(1, 2), "otra": Costos(1, 1)})
    p = modelo.predecir(1, "pan", D)
    assert p.venta_esperada == 20
    assert p.cantidad_sugerida == 10
    assert p.muestras == 2
    assert p.estrategia == "mismo_dia_semana"


def test_excluye_dia_actual_futuro_y_fuera_de_ventana():
    modelo = BaselineSemanal([venta(-63, 9000), venta(-56, 10), venta(-7, 30),
                              venta(0, 50000), venta(7, 90000)], {"pan": Costos(1, 1)})
    assert modelo.predecir(1, "pan", D).venta_esperada == 20


def test_fallback_reciente_sin_rellenar_preapertura():
    modelo = BaselineSemanal([venta(-2, 10), venta(-1, 30)], {"pan": Costos(1, 1)})
    p = modelo.predecir(1, "pan", D)
    assert p.venta_esperada == 20 and p.estrategia == "historial_reciente"
    with pytest.raises(ValueError, match="Sin historial"):
        modelo.predecir(2, "pan", D)


@pytest.mark.parametrize("costos", [Costos(1, 0.1), Costos(1, 2.5), Costos(0, 2), Costos(2, 0), Costos(1, 1)])
def test_cuantil_minimiza_costo_empirico(costos):
    muestra = [0, 2, 2, 5, 9, 10]
    sugerido = cantidad_optima(muestra, costos)
    objetivo = lambda q: sum(costo_negocio(y, q, costos) for y in muestra)
    assert objetivo(sugerido) == pytest.approx(min(objetivo(q) for q in range(12)))
    assert type(sugerido) is int and sugerido >= 0


def test_costos_asimetricos_cambian_sugerido():
    muestra = list(range(10, 110, 10))
    assert cantidad_optima(muestra, Costos(2, 0.1)) > cantidad_optima(muestra, Costos(1, 2.5))
    assert costo_negocio(10, 7, Costos(2, 3)) == 6
    assert costo_negocio(10, 12, Costos(2, 3)) == 6


@pytest.mark.parametrize("faltante,sobrante", [(-1, 1), (1, -1), (0, 0), (float("nan"), 1), (1, float("inf"))])
def test_costos_invalidos(faltante, sobrante):
    with pytest.raises(ValueError):
        Costos(faltante, sobrante)


def test_agregar_rechaza_duplicados_sin_modificar_modelo():
    modelo = BaselineSemanal([venta(-7, 10)], {"pan": Costos(1, 1)})
    with pytest.raises(ValueError, match="duplicada"):
        modelo.agregar([venta(-1, 100), venta(-7, 20)])
    assert modelo.predecir(1, "pan", D + timedelta(days=1)).venta_esperada == 10


def test_walk_forward_solo_observa_pasado():
    historial = [venta(-7, 10), venta(0, 20), venta(7, 1000), venta(14, 99999)]
    reporte, filas = evaluar_temporal(historial, {"pan": Costos(1, 1)}, D, D + timedelta(days=7))
    assert [f["venta_esperada"] for f in filas] == [10, 15]
    assert reporte["entrenamiento_hasta"] < reporte["inicio"]
    assert reporte["metricas"]["registros"] == 2
    # Alterar ventas del día evaluado y del futuro no altera su propia predicción.
    _, alteradas = evaluar_temporal([venta(-7, 10), venta(0, 20), venta(7, 1), venta(14, 0)],
                                   {"pan": Costos(1, 1)}, D, D + timedelta(days=7))
    assert [f["venta_esperada"] for f in alteradas] == [10, 15]


def test_metricas_conocidas_y_demanda_cero():
    filas = [{"real": 10, "venta_esperada": 8, "costo": 4, "costo_media": 4},
             {"real": 0, "venta_esperada": 2, "costo": 6, "costo_media": 6}]
    m = metricas(filas)
    assert m["mae"] == 2 and m["rmse"] == 2 and m["wape"] == 0.4
    assert m["costo_total"] == 10 and m["costo_medio"] == 5
    assert metricas([{**filas[1], "real": 0}])["wape"] is None


@pytest.mark.parametrize("historial,inicio,fin", [
    ([venta(0, 10)], D, D),
    ([venta(-7, 10)], D, D),
    ([venta(-7, 10), venta(0, 1), venta(0, 1)], D, D),
    ([venta(-7, 10)], D, D - timedelta(days=1))])
def test_validacion_no_acepta_evaluaciones_invalidas(historial, inicio, fin):
    with pytest.raises(ValueError):
        evaluar_temporal(historial, {"pan": Costos(1, 1)}, inicio, fin)


def test_carga_csv_y_rechaza_duplicados(tmp_path):
    (tmp_path / "costos.csv").write_text("familia_id,costo_faltante,costo_sobrante\npan,1,2\n")
    (tmp_path / "familias.csv").write_text("familia_id,nombre\npan,Pan\n")
    (tmp_path / "tiendas.csv").write_text("tienda_id,fecha_apertura\n1,2025-01-01\n")
    archivo = tmp_path / "historico_ventas.csv"
    cabecera = "fecha,tienda_id,familia_id,ventas,en_promocion\n"
    fila = "2026-01-01,1,pan,10,0\n"
    archivo.write_text(cabecera + fila)
    historial, costos = cargar_datos(tmp_path)
    assert len(historial) == 1 and costos["pan"].sobrante == 2
    archivo.write_text(cabecera + fila + fila)
    with pytest.raises(ValueError, match="Duplicados"):
        cargar_datos(tmp_path)
