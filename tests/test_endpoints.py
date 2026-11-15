import copy

import pytest
from fastapi.testclient import TestClient

from app.api.dependencias import obtener_catalogos, obtener_predictor, obtener_registro, obtener_registro_predicciones
from app.calidad.normalizacion import Catalogos
from app.main import crear_app
from app.servicios.interfaces import ServicioNoDisponible


class PredictorPrueba:
    def __init__(self):
        self.llamadas = []
        self.resultado = {"version_modelo": "3", "predicciones": [
            {"familia_id": "abarrotes", "venta_esperada": 612.4, "cantidad_sugerida": 640},
            {"familia_id": "lacteos", "venta_esperada": 100.0, "cantidad_sugerida": 90}]}

    def predecir(self, solicitud):
        self.llamadas.append(solicitud)
        return self.resultado


class RegistroPrueba:
    """Solo un doble programado: no afirma ni simula persistencia real."""
    def __init__(self):
        self.llamadas = []
        self.conteo = 1

    def guardar(self, original, solicitud, calidad):
        self.llamadas.append((original, solicitud, calidad))
        return self.conteo

    def guardar_prediccion(self, original, solicitud, calidad, resultado):
        self.llamadas.append((original, solicitud, calidad, resultado))


@pytest.fixture
def entorno(monkeypatch):
    # Las pruebas aisladas nunca deben usar una DB configurada en el shell.
    for clave in ("PRODUCT_DB_HOST", "PRODUCT_DB_NAME", "PRODUCT_DB_USER", "PRODUCT_DB_PASSWORD"):
        monkeypatch.delenv(clave, raising=False)
    app = crear_app()
    predictor, registro = PredictorPrueba(), RegistroPrueba()
    app.dependency_overrides[obtener_catalogos] = lambda: Catalogos(
        frozenset({5}), frozenset({"abarrotes", "lacteos"}),
        {"abarrotes": "abarrotes", "lacteos": "lacteos"})
    app.dependency_overrides[obtener_predictor] = lambda: predictor
    app.dependency_overrides[obtener_registro] = lambda: registro
    app.dependency_overrides[obtener_registro_predicciones] = lambda: registro
    with TestClient(app) as cliente:
        yield cliente, predictor, registro, app


def prediccion():
    return {"tienda_id": 5, "fecha": "2025-11-17", "familias": [
        {"familia_id": "abarrotes", "en_promocion": 0},
        {"familia_id": "lacteos", "en_promocion": 8}]}


def observacion():
    return {"tienda_id": 5, "fecha": "2025-11-17", "ventas": [
        {"familia_id": "abarrotes", "ventas": 994}]}


def test_prediccion_200_contrato_y_repeticion(entorno):
    cliente, predictor, _, _ = entorno
    for _ in range(2):
        respuesta = cliente.post("/v1/prediccion", json=prediccion())
        assert respuesta.status_code == 200
        assert respuesta.json() == {"tienda_id": 5, "fecha": "2025-11-17",
            **predictor.resultado, "calidad": {"estado": "ok", "observaciones": []}}
    assert len(predictor.llamadas) == 2


def test_prediccion_reparada_y_parcial(entorno):
    cliente, predictor, _, _ = entorno
    entrada = prediccion()
    entrada["tienda_id"] = "T05"
    entrada["fecha"] = "17/11/2025"
    entrada["familias"] = [{"familia_id": "LÁCTEOS ", "en_promocion": "8"}]
    predictor.resultado["predicciones"] = predictor.resultado["predicciones"][1:]
    respuesta = cliente.post("/v1/prediccion", json=entrada)
    assert respuesta.status_code == 200
    assert respuesta.json()["calidad"]["estado"] == "advertencia"
    assert all(set(a) == {"campo", "accion", "detalle"} for a in respuesta.json()["calidad"]["observaciones"])
    assert predictor.llamadas[0].familias[0].familia_id == "lacteos"
    assert predictor.llamadas[0].familias[0].en_promocion == 8


def test_observaciones_200_conteo_proveedor_y_original(entorno):
    cliente, _, registro, _ = entorno
    entrada = observacion()
    entrada["ventas"][0]["ventas"] = "994"
    respuesta = cliente.post("/v1/observaciones", json=entrada)
    assert respuesta.status_code == 200
    assert respuesta.json()["registros_guardados"] == 1
    assert respuesta.json()["calidad"]["estado"] == "corregido"
    original, canonico, calidad = registro.llamadas[0]
    assert original == entrada
    assert canonico.ventas[0].ventas == 994
    assert calidad.model_dump() == respuesta.json()["calidad"]
    registro.conteo = 0  # Respuesta programada del puerto, no prueba de idempotencia DB.
    respuesta = cliente.post("/v1/observaciones", json=entrada)
    assert respuesta.status_code == 200
    assert respuesta.json()["registros_guardados"] == 0


@pytest.mark.parametrize("ruta,fabrica", [("prediccion", prediccion), ("observaciones", observacion)])
@pytest.mark.parametrize("defecto", ["tienda", "fecha", "familia", "negativo", "ambiguo", "duplicado", "extra", "vacio"])
def test_rechazo_422_no_invoca_proveedores(entorno, ruta, fabrica, defecto):
    cliente, predictor, registro, _ = entorno
    entrada = fabrica()
    lista, medida = ("familias", "en_promocion") if ruta == "prediccion" else ("ventas", "ventas")
    if defecto == "tienda": entrada["tienda_id"] = 999
    if defecto == "fecha": entrada["fecha"] = "2025-02-30"
    if defecto == "familia": entrada[lista][0]["familia_id"] = "desconocida"
    if defecto == "negativo": entrada[lista][0][medida] = -4
    if defecto == "ambiguo": entrada[lista][0][medida] = "1,292"
    if defecto == "duplicado":
        otro = copy.deepcopy(entrada[lista][0]); otro[medida] += 1; entrada[lista].append(otro)
    if defecto == "extra": entrada["campo_extra"] = 1
    if defecto == "vacio": entrada[lista] = []
    respuesta = cliente.post(f"/v1/{ruta}", json=entrada)
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]
    assert not predictor.llamadas and not registro.llamadas


@pytest.mark.parametrize("ruta", ["prediccion", "observaciones"])
@pytest.mark.parametrize("cuerpo", ["{", "null", "[]", "5", '"texto"', "{}"])
def test_cuerpo_invalido_422(entorno, ruta, cuerpo):
    cliente, predictor, registro, _ = entorno
    respuesta = cliente.post(f"/v1/{ruta}", content=cuerpo, headers={"Content-Type": "application/json"})
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]
    assert not predictor.llamadas and not registro.llamadas


@pytest.mark.parametrize("ruta,fabrica,dependencia", [
    ("prediccion", prediccion, obtener_predictor),
    ("observaciones", observacion, obtener_registro)])
def test_sin_backend_no_inventa_exito(entorno, ruta, fabrica, dependencia):
    cliente, _, _, app = entorno
    del app.dependency_overrides[dependencia]
    respuesta = cliente.post(f"/v1/{ruta}", json=fabrica())
    assert respuesta.status_code == 503
    assert set(respuesta.json()) == {"detail"}
    entrada = fabrica(); entrada["tienda_id"] = 999
    assert cliente.post(f"/v1/{ruta}", json=entrada).status_code == 422


@pytest.mark.parametrize("resultado", [
    {"version_modelo": "3", "predicciones": []},
    {"version_modelo": "3", "predicciones": [{"familia_id": "otra", "venta_esperada": 1.0, "cantidad_sugerida": 1}]},
    {"version_modelo": 3, "predicciones": []}])
def test_resultado_predictor_invalido_no_es_200(entorno, resultado):
    cliente, predictor, _, _ = entorno
    predictor.resultado = resultado
    assert cliente.post("/v1/prediccion", json=prediccion()).status_code == 503


@pytest.mark.parametrize("conteo", [-1, True, 2, None])
def test_conteo_invalido_no_se_confirma(entorno, conteo):
    cliente, _, registro, _ = entorno
    registro.conteo = conteo
    assert cliente.post("/v1/observaciones", json=observacion()).status_code == 503


def test_catalogos_ausentes_503(entorno, monkeypatch, tmp_path):
    cliente, predictor, registro, app = entorno
    del app.dependency_overrides[obtener_catalogos]
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert cliente.post("/v1/prediccion", json=prediccion()).status_code == 503
    assert not predictor.llamadas and not registro.llamadas


def test_fallo_de_proveedor_503(entorno):
    cliente, _, _, app = entorno
    class Fallo:
        def predecir(self, solicitud):
            raise ServicioNoDisponible("Proveedor temporalmente no disponible")
    app.dependency_overrides[obtener_predictor] = Fallo
    respuesta = cliente.post("/v1/prediccion", json=prediccion())
    assert respuesta.status_code == 503
    assert respuesta.json()["detail"]


def test_no_responde_prediccion_si_no_puede_registrarla(entorno):
    cliente, predictor, _, app = entorno
    class RegistroFallido:
        def guardar_prediccion(self, original, solicitud, calidad, resultado):
            raise ServicioNoDisponible("No se pudo confirmar el registro de la predicción")
    app.dependency_overrides[obtener_registro_predicciones] = RegistroFallido
    respuesta = cliente.post("/v1/prediccion", json=prediccion())
    assert predictor.llamadas
    assert respuesta.status_code == 503
    assert "predicciones" not in respuesta.json()
