"""Integración real. TEST_PRODUCT_DB_DSN apunta a un servidor exclusivo de pruebas.

Se crea y elimina una base temporal; nunca se truncan tablas de la base indicada.
"""

from concurrent.futures import ThreadPoolExecutor
import os
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from app.calidad.normalizacion import Catalogos, normalizar_observaciones, normalizar_prediccion
from app.db.migrar import aplicar_esquema
from app.db.repositorio import RepositorioProducto
from app.schemas.respuestas import ResultadoPrediccion
from app.servicios.interfaces import ServicioNoDisponible


@pytest.fixture(scope="module")
def servidor():
    dsn = os.environ.get("TEST_PRODUCT_DB_DSN")
    if not dsn:
        pytest.skip("Definir TEST_PRODUCT_DB_DSN para integración PostgreSQL real")
    nombre = "test_novamercado_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nombre)))
    test_dsn = make_conninfo(dsn, dbname=nombre)
    conectar = lambda: psycopg.connect(test_dsn)
    try:
        aplicar_esquema(conectar)
        aplicar_esquema(conectar)  # Inicialización repetible sin pérdida de datos.
        yield conectar
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(nombre)))


@pytest.fixture
def db(servidor):
    with servidor() as conexion:
        conexion.execute("TRUNCATE novamercado.solicitudes CASCADE")
    return servidor


def entrada(ventas=994):
    return {"tienda_id": "T05", "fecha": "17/11/2025", "ventas": [
        {"familia_id": "LÁCTEOS", "ventas": ventas}]}


def catalogos():
    return Catalogos(frozenset({5}), frozenset({"lacteos"}), {"lacteos": "lacteos"})


def guardar(repo, original):
    solicitud, calidad = normalizar_observaciones(original, catalogos())
    return repo.guardar(original, solicitud, calidad)


def test_reenvio_y_correccion_con_historial(db):
    repo = RepositorioProducto(db)
    assert guardar(repo, entrada()) == 1
    assert guardar(repo, entrada()) == 0
    assert guardar(repo, entrada(1000)) == 1
    assert guardar(repo, entrada(1000)) == 0
    with db() as conexion:
        assert conexion.execute("SELECT ventas FROM novamercado.observaciones").fetchall() == [(1000,)]
        assert conexion.execute("SELECT count(*) FROM novamercado.historial_observaciones").fetchone() == (2,)
        assert conexion.execute("SELECT count(*) FROM novamercado.solicitudes").fetchone() == (4,)
        original, canonica, estado = conexion.execute(
            "SELECT original, canonica, calidad_estado FROM novamercado.solicitudes LIMIT 1").fetchone()
        assert original["tienda_id"] == "T05" and canonica["tienda_id"] == 5
        assert estado == "corregido"
        assert conexion.execute("SELECT count(*) FROM novamercado.acciones_calidad").fetchone()[0] == 12


def test_reenvios_concurrentes(db):
    with ThreadPoolExecutor(max_workers=4) as pool:
        conteos = list(pool.map(lambda _: guardar(RepositorioProducto(db), entrada()), range(8)))
    assert sorted(conteos) == [0] * 7 + [1]
    with db() as conexion:
        assert conexion.execute("SELECT count(*) FROM novamercado.observaciones").fetchone() == (1,)
        assert conexion.execute("SELECT count(*) FROM novamercado.historial_observaciones").fetchone() == (1,)


def test_predicciones_multiples_y_version_por_resultado(db):
    original = {"tienda_id": 5, "fecha": "2025-11-17", "familias": [
        {"familia_id": "LÁCTEOS", "en_promocion": "2"}]}
    solicitud, calidad = normalizar_prediccion(original, catalogos())
    repo = RepositorioProducto(db)
    ids = []
    for version in ["3", "4"]:
        resultado = ResultadoPrediccion(version_modelo=version, predicciones=[{
            "familia_id": "lacteos", "venta_esperada": 100.5, "cantidad_sugerida": 90}])
        ids.append(repo.guardar_prediccion(original, solicitud, calidad, resultado))
    assert ids[0] != ids[1]
    aplicar_esquema(db)
    with db() as conexion:
        assert conexion.execute("SELECT version_modelo FROM novamercado.predicciones ORDER BY version_modelo").fetchall() == [("3",), ("4",)]
        assert conexion.execute("SELECT count(*) FROM novamercado.acciones_calidad").fetchone() == (4,)


def test_rollback_total_si_un_item_falla(db):
    original = entrada()
    # Segundo elemento válido en contrato pero fuera del rango bigint de PostgreSQL.
    cats = Catalogos(frozenset({5}), frozenset({"lacteos", "z"}), {"lacteos": "lacteos", "z": "z"})
    original["ventas"].append({"familia_id": "z", "ventas": 2**64})
    solicitud, calidad = normalizar_observaciones(original, cats)
    with pytest.raises(ServicioNoDisponible):
        RepositorioProducto(db).guardar(original, solicitud, calidad)
    with db() as conexion:
        for tabla in ["solicitudes", "observaciones", "historial_observaciones", "acciones_calidad"]:
            assert conexion.execute(sql.SQL("SELECT count(*) FROM novamercado.{}").format(sql.Identifier(tabla))).fetchone() == (0,)


def test_lote_cuenta_solo_nuevos_y_modificados(db):
    repo = RepositorioProducto(db)
    assert guardar(repo, entrada()) == 1
    original = entrada(1000)  # Una modificación y una familia nueva en el mismo lote.
    original["ventas"].append({"familia_id": "z", "ventas": 10})
    cats = Catalogos(frozenset({5}), frozenset({"lacteos", "z"}), {"lacteos": "lacteos", "z": "z"})
    solicitud, calidad = normalizar_observaciones(original, cats)
    assert repo.guardar(original, solicitud, calidad) == 2
    assert repo.guardar(original, solicitud, calidad) == 0


def test_observaciones_http_con_postgres(db):
    from fastapi.testclient import TestClient
    from app.main import crear_app
    from app.api.dependencias import obtener_catalogos, obtener_registro
    app = crear_app()
    app.dependency_overrides[obtener_catalogos] = lambda: Catalogos(
        frozenset({5}), frozenset({"lacteos", "z"}), {"lacteos": "lacteos", "z": "z"})
    app.dependency_overrides[obtener_registro] = lambda: RepositorioProducto(db)
    with TestClient(app) as cliente:
        lote = entrada(1000)
        lote["ventas"].append({"familia_id": "z", "ventas": 10})
        for cuerpo, esperado in [(entrada(), 1), (entrada(), 0), (lote, 2), (lote, 0)]:
            respuesta = cliente.post("/v1/observaciones", json=cuerpo)
            assert respuesta.status_code == 200
            assert respuesta.json()["registros_guardados"] == esperado


def test_error_conexion_no_confirma_guardado():
    def fallo():
        raise psycopg.OperationalError("secreto que no debe aparecer en HTTP")
    with pytest.raises(ServicioNoDisponible, match="No se pudo confirmar") as error:
        guardar(RepositorioProducto(fallo), entrada())
    assert "secreto" not in str(error.value)


def test_fallo_commit_no_devuelve_conteo():
    class TransaccionFallida:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            raise psycopg.OperationalError("falló commit")

        def execute(self, *args):
            return self

        def fetchone(self):
            return ("lacteos",)

    with pytest.raises(ServicioNoDisponible):
        guardar(RepositorioProducto(TransaccionFallida), entrada())


@pytest.fixture
def api_real(db, monkeypatch, tmp_path):
    """Cableado de producción: sin dependency_overrides ni repositorios sustitutos."""
    from fastapi.testclient import TestClient
    from app.main import crear_app

    with db() as conexion:
        for variable, valor in {
            "PRODUCT_DB_HOST": conexion.info.host,
            "PRODUCT_DB_PORT": str(conexion.info.port),
            "PRODUCT_DB_NAME": conexion.info.dbname,
            "PRODUCT_DB_USER": conexion.info.user,
            "PRODUCT_DB_PASSWORD": conexion.info.password,
        }.items():
            monkeypatch.setenv(variable, valor)
    # Catálogos mínimos locales. No se requiere GES para probar el cableado real.
    (tmp_path / "tiendas.csv").write_text("tienda_id\n5\n")
    (tmp_path / "familias.csv").write_text("familia_id,nombre\nlacteos,Lácteos\nz,Z\n")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AIRFLOW__DATABASE__SQL_ALCHEMY_CONN", "postgresql://no-usar/airflow")
    app = crear_app()
    assert app.dependency_overrides == {}
    with TestClient(app) as cliente:
        yield cliente, db


def test_cableado_real_observaciones_nuevos_modificados_e_identicos(api_real):
    cliente, conectar = api_real
    lote = entrada(1000)
    lote["ventas"].append({"familia_id": "z", "ventas": 10})
    for cuerpo, esperado in [(entrada(), 1), (entrada(), 0), (lote, 2), (lote, 0)]:
        respuesta = cliente.post("/v1/observaciones", json=cuerpo)
        assert respuesta.status_code == 200
        assert respuesta.json()["registros_guardados"] == esperado
        assert respuesta.json()["calidad"]["estado"] == "corregido"
    with conectar() as conexion:
        assert conexion.execute("SELECT familia_id, ventas FROM novamercado.observaciones ORDER BY familia_id").fetchall() == [("lacteos", 1000), ("z", 10)]
        assert conexion.execute("SELECT count(*) FROM novamercado.historial_observaciones").fetchone() == (3,)
        assert conexion.execute("SELECT count(*) FROM novamercado.solicitudes").fetchone() == (4,)


def test_cableado_real_prediccion_sin_modelo_y_rechazo_sin_escrituras(api_real):
    cliente, conectar = api_real
    solicitud = {"tienda_id": 5, "fecha": "2025-11-17", "familias": [
        {"familia_id": "lacteos", "en_promocion": 0}]}
    respuesta = cliente.post("/v1/prediccion", json=solicitud)
    assert respuesta.status_code == 503
    assert respuesta.json() == {"detail": "No hay modelo champion cargado"}
    respuesta = cliente.post("/v1/observaciones", json=entrada(-4))
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]
    with conectar() as conexion:
        assert conexion.execute("SELECT count(*) FROM novamercado.solicitudes").fetchone() == (0,)
        assert conexion.execute("SELECT count(*) FROM novamercado.predicciones").fetchone() == (0,)


def test_cableado_real_error_db_no_confirma_guardado(api_real, monkeypatch):
    cliente, conectar = api_real
    monkeypatch.setenv("PRODUCT_DB_NAME", "base_inexistente_" + uuid4().hex)
    respuesta = cliente.post("/v1/observaciones", json=entrada())
    assert respuesta.status_code == 503
    assert set(respuesta.json()) == {"detail"}
    with conectar() as conexion:
        assert conexion.execute("SELECT count(*) FROM novamercado.solicitudes").fetchone() == (0,)


def test_prediccion_champion_real_persistida_y_continua_sin_mlflow(api_real, modelo_serving, monkeypatch):
    from app.schemas.solicitudes import SolicitudPrediccion
    from datetime import date

    cliente, conectar = api_real
    monkeypatch.setenv("DATA_DIR", str(modelo_serving.data_dir))
    for fecha, ventas in [("2026-01-08", 123), ("2026-01-09", 99999)]:
        r = cliente.post("/v1/observaciones", json={"tienda_id": 5, "fecha": fecha,
            "ventas": [{"familia_id": "pan", "ventas": ventas}]})
        assert r.status_code == 200
    entrada = {"tienda_id": "T05", "fecha": "09/01/2026",
               "familias": [{"familia_id": "PAN", "en_promocion": "2"}]}
    primera = cliente.post("/v1/prediccion", json=entrada)
    assert primera.status_code == 200, primera.text
    contenido = primera.json()
    assert contenido["version_modelo"] == modelo_serving.version
    assert contenido["calidad"]["estado"] == "corregido"
    predictor = cliente.app.state.predictor
    snapshot = predictor.cache.obtener()
    solicitud = SolicitudPrediccion(tienda_id=5, fecha=date(2026, 1, 9), familias=[{"familia_id": "pan", "en_promocion": 2}])
    x = predictor.variables.matriz(solicitud, snapshot)
    assert x.loc[0, "lag_1"] == 123  # DB reemplaza histórico; observación de D se excluye.
    esperadas = modelo_serving.modelo.predict(None, x)
    assert contenido["predicciones"] == [{"familia_id": "pan",
        "venta_esperada": float(esperadas.iloc[0].venta_esperada),
        "cantidad_sugerida": int(esperadas.iloc[0].cantidad_sugerida)}]

    def no_disponible():
        raise ConnectionError("MLflow temporalmente no disponible")
    monkeypatch.setattr(predictor.cache.fuente, "consultar", no_disponible)
    predictor.cache.refrescar()
    assert predictor.cache.ultimo_error == "ConnectionError"
    segunda = cliente.post("/v1/prediccion", json=entrada)
    assert segunda.status_code == 200 and segunda.json() == contenido
    with conectar() as conexion:
        filas = conexion.execute("SELECT version_modelo, venta_esperada, cantidad_sugerida FROM novamercado.predicciones").fetchall()
        assert len(filas) == 2
        assert all(f == (modelo_serving.version, contenido["predicciones"][0]["venta_esperada"],
                         contenido["predicciones"][0]["cantidad_sugerida"]) for f in filas)
    # Un segundo request reutiliza el mismo servicio y snapshot cargado.
    assert cliente.app.state.predictor is predictor
