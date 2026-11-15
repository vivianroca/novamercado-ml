import csv
from datetime import date

import pytest

from ml.features import construir_matriz, NOMBRES
from ml.reentrenamiento import construir_snapshot

@pytest.fixture
def datos(tmp_path):
    d = tmp_path / "original"
    d.mkdir()
    (d / "tiendas.csv").write_text("tienda_id,nombre,ciudad,departamento,tipo,fecha_apertura\n5,Prueba,Guatemala,Guatemala,express,2024-01-01\n")
    (d / "familias.csv").write_text("familia_id,nombre\npan,Pan\n")
    (d / "costos.csv").write_text("familia_id,costo_faltante,costo_sobrante\npan,1,2\n")
    (d / "feriados.csv").write_text("fecha,nombre,tipo,ambito\n2026-01-01,Feriado,feriado,nacional\n")
    (d / "historico_ventas.csv").write_text("fecha,tienda_id,familia_id,ventas,en_promocion\n2026-01-01,5,pan,10,2\n2026-01-02,5,pan,12,0\n")
    return d


def test_reconciliacion_por_clave_y_promociones_sin_inventar(datos, tmp_path):
    original = (datos / "historico_ventas.csv").read_bytes()
    observaciones = [(date(2026, 1, 1), 5, "pan", 20), (date(2026, 1, 3), 5, "pan", 30),
                     (date(2026, 1, 4), 5, "pan", 40)]
    solicitudes = [{"fecha": "2026-01-03", "tienda_id": 5, "familias": [{"familia_id": "pan", "en_promocion": 3}]}]
    salida = tmp_path / "snapshot"
    m = construir_snapshot(datos, salida, observaciones, solicitudes)
    with (salida / "historico_ventas.csv").open() as f:
        filas = list(csv.DictReader(f))
    assert len(filas) == 4 and filas[0]["ventas"] == "20" and filas[0]["en_promocion"] == "2"
    assert filas[2]["en_promocion"] == "3" and filas[3]["en_promocion"] == ""
    assert m["filas_nuevas"] == 2 and m["filas_corregidas"] == 1 and m["promociones_no_disponibles"] == 1
    assert (datos / "historico_ventas.csv").read_bytes() == original
    import numpy as np
    x, _, _ = construir_matriz(salida)
    assert np.isnan(x[-1, NOMBRES.index("en_promocion")])


def test_snapshot_idempotente_y_corte_simulado(datos, tmp_path):
    observaciones = [(date(2026, 1, 1), 5, "pan", 20), (date(2030, 1, 1), 5, "pan", 999)]
    a = construir_snapshot(datos, tmp_path / "a", observaciones, [], date(2026, 1, 1))
    b = construir_snapshot(datos, tmp_path / "b", observaciones, [], date(2026, 1, 1))
    assert a == b and a["registros"] == 1 and a["fecha_fin_efectiva"] == "2026-01-01"
    assert (tmp_path / "a/historico_ventas.csv").read_bytes() == (tmp_path / "b/historico_ventas.csv").read_bytes()


def test_snapshot_rechaza_duplicados(datos, tmp_path):
    obs = (date(2026, 1, 1), 5, "pan", 10)
    with pytest.raises(ValueError, match="duplicadas"):
        construir_snapshot(datos, tmp_path / "snapshot", [obs, obs], [])


def test_dag_parseo_serializacion_sdk_332(ejecutar_sdk_airflow):
    r = ejecutar_sdk_airflow()
    assert r["airflow"] == "3.3.2" and r["parseo_y_serializacion"] == "ok"
