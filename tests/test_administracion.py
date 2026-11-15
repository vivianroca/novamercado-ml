import json

from fastapi.testclient import TestClient
import httpx
import pytest

from app.api.dependencias import obtener_reentrenamientos
from app.main import crear_app
from app.servicios.reentrenamientos import ClienteReentrenamientos

DAG = "/api/v2/dags/novamercado_reentrenamiento"


class AirflowSimulado:
    def __init__(self):
        self.llamadas = []
        self.paused = True
        self.errores = False
        self.auth_status = 201
        self.meta_status = self.patch_status = self.trigger_status = 200
        self.xcom_status = 200
        self.malformado = False
        self.id_incorrecto = False
        self.timeout = False
        self.confirmar_timeout = True
        self.runs = {"conocido": "running"}
        self.resultado = {"estado": "exitoso", "promovido": False, "version": "3", "motivo": "Costo sin mejora"}

    def responder(self, r):
        self.llamadas.append(r)
        if r.url.path == "/auth/token":
            assert json.loads(r.content) == {"username": "pruebas", "password": "clave-sintetica"}
            return httpx.Response(self.auth_status, json={"access_token": "jwt-simulado"})
        assert r.headers["Authorization"] == "Bearer jwt-simulado"
        if r.url.path == DAG:
            if r.method == "PATCH":
                assert json.loads(r.content) == {"is_paused": False}
                self.paused = False
                return httpx.Response(self.patch_status, json={"is_paused": False})
            return httpx.Response(self.meta_status, json=[] if self.malformado else {
                "dag_id": "novamercado_reentrenamiento", "is_paused": self.paused, "has_import_errors": self.errores})
        if r.url.path == DAG + "/dagRuns":
            assert r.method == "POST"
            cuerpo = json.loads(r.content)
            assert cuerpo["logical_date"] is None and cuerpo["conf"] == {}
            identificador = cuerpo["dag_run_id"]
            if self.confirmar_timeout:
                self.runs[identificador] = "queued"
            if self.timeout:
                raise httpx.ReadTimeout("respuesta perdida", request=r)
            return httpx.Response(self.trigger_status, json={"dag_run_id": "otro" if self.id_incorrecto else identificador})
        identificador = r.url.path[len(DAG + "/dagRuns/"):].split("/taskInstances/")[0]
        if identificador not in self.runs:
            return httpx.Response(404, json={"detail": "no existe"})
        if "/xcomEntries/" in r.url.path:
            assert r.url.params["deserialize"] == "true"
            assert r.url.params["stringify"] == "false"
            assert r.url.path.endswith("/finalizar_reentrenamiento/xcomEntries/resultado_reentrenamiento")
            return httpx.Response(self.xcom_status, json={"value": self.resultado})
        return httpx.Response(200, json={"dag_run_id": identificador, "state": self.runs[identificador],
                                        "candidate_version": "99"})


@pytest.fixture
def entorno():
    simulado = AirflowSimulado()
    servicio = ClienteReentrenamientos("http://airflow.simulado", "pruebas", "clave-sintetica",
                                       transporte=httpx.MockTransport(simulado.responder))
    app = crear_app()
    app.dependency_overrides[obtener_reentrenamientos] = lambda: servicio
    with TestClient(app) as cliente:
        yield cliente, simulado, app


def test_iniciar_202_id_texto_y_airflow_v2(entorno):
    cliente, airflow, _ = entorno
    respuesta = cliente.post("/admin/reentrenar")
    assert respuesta.status_code == 202
    identificador = respuesta.json()["id"]
    assert isinstance(identificador, str) and identificador in airflow.runs
    assert [r.method for r in airflow.llamadas] == ["POST", "GET", "PATCH", "POST"]


def test_dag_activo_no_se_modifica_y_cada_inicio_tiene_id_distinto(entorno):
    cliente, airflow, _ = entorno
    airflow.paused = False
    a = cliente.post("/admin/reentrenar")
    b = cliente.post("/admin/reentrenar")
    assert a.status_code == b.status_code == 202
    assert a.json()["id"] != b.json()["id"]
    assert not any(r.method == "PATCH" for r in airflow.llamadas)


@pytest.mark.parametrize("cuerpo", ["{}", "null", "[]", "texto"])
def test_inicio_no_admite_cuerpo_422_sin_contactar_airflow(entorno, cuerpo):
    cliente, airflow, _ = entorno
    r = cliente.post("/admin/reentrenar", content=cuerpo)
    assert r.status_code == 422 and r.json()["detail"]
    assert airflow.llamadas == []


@pytest.mark.parametrize("defecto", ["auth", "dag404", "importacion", "patch", "post", "malformado", "id"])
def test_inicio_no_confirmado_503(entorno, defecto):
    cliente, a, _ = entorno
    if defecto == "auth": a.auth_status = 401
    if defecto == "dag404": a.meta_status = 404
    if defecto == "importacion": a.errores = True
    if defecto == "patch": a.patch_status = 403
    if defecto == "post": a.trigger_status = 500
    if defecto == "malformado": a.malformado = True
    if defecto == "id": a.id_incorrecto = True
    r = cliente.post("/admin/reentrenar")
    assert r.status_code == 503 and set(r.json()) == {"detail"}
    assert "clave-sintetica" not in r.text and "jwt-simulado" not in r.text


@pytest.mark.parametrize("confirmado,codigo", [(True, 202), (False, 503)])
def test_timeout_no_duplica_trigger_y_verifica_id(entorno, confirmado, codigo):
    cliente, a, _ = entorno
    a.timeout, a.confirmar_timeout = True, confirmado
    r = cliente.post("/admin/reentrenar")
    assert r.status_code == codigo
    assert sum(r.method == "POST" and r.url.path == DAG + "/dagRuns" for r in a.llamadas) == 1


@pytest.mark.parametrize("estado", ["queued", "running"])
def test_queued_y_running_son_en_curso_sin_campos_terminales(entorno, estado):
    cliente, a, _ = entorno
    a.runs["conocido"] = estado
    r = cliente.get("/admin/reentrenar/conocido")
    assert r.status_code == 200 and r.json() == {"estado": "en_curso"}
    assert len(a.llamadas) == 2


@pytest.mark.parametrize("estado,promovido,version", [("success", True, "4"), ("success", False, "3"), ("failed", False, "3")])
def test_terminal_version_vigente_no_candidata(entorno, estado, promovido, version):
    cliente, a, _ = entorno
    a.runs["conocido"] = estado
    a.resultado = {"estado": "exitoso" if estado == "success" else "fallido", "promovido": promovido,
                   "version": version, "motivo": "Decisión histórica al terminar", "evaluacion_run_id": "auditoria"}
    r = cliente.get("/admin/reentrenar/conocido")
    assert r.status_code == 200
    assert r.json() == {k: a.resultado[k] for k in ("estado", "promovido", "version", "motivo")}
    assert r.json()["version"] != "99"
    assert all(req.method == "GET" for req in a.llamadas[1:])


def test_id_desconocido_404(entorno):
    cliente, _, _ = entorno
    r = cliente.get("/admin/reentrenar/no-existe")
    assert r.status_code == 404 and r.json()["detail"]


@pytest.mark.parametrize("defecto", ["xcom404", "version_nula", "version_numero", "promovido_texto", "estado_distinto", "sin_motivo", "valor_texto", "estado_airflow"])
def test_resultado_incompleto_o_inconsistente_503_sin_inventar(entorno, defecto):
    cliente, a, _ = entorno
    a.runs["conocido"] = "success"
    if defecto == "xcom404": a.xcom_status = 404
    if defecto == "version_nula": a.resultado["version"] = None
    if defecto == "version_numero": a.resultado["version"] = 3
    if defecto == "promovido_texto": a.resultado["promovido"] = "false"
    if defecto == "estado_distinto": a.resultado["estado"] = "fallido"
    if defecto == "sin_motivo": del a.resultado["motivo"]
    if defecto == "valor_texto": a.resultado = "{'estado': 'exitoso'}"
    if defecto == "estado_airflow": a.runs["conocido"] = "desconocido"
    r = cliente.get("/admin/reentrenar/conocido")
    assert r.status_code == 503 and set(r.json()) == {"detail"}


@pytest.mark.parametrize("ruta", ["/admin/reentrenar", "/admin/reentrenar/conocido"])
def test_airflow_real_bloqueado_por_fixture(entorno, ruta, monkeypatch):
    cliente, a, app = entorno
    del app.dependency_overrides[obtener_reentrenamientos]
    monkeypatch.setenv("AIRFLOW_BASE_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("AIRFLOW_USER", "pruebas")
    monkeypatch.setenv("AIRFLOW_PASSWORD", "clave-sintetica")
    r = cliente.post(ruta) if ruta.endswith("/reentrenar") else cliente.get(ruta)
    assert r.status_code == 503
    assert a.llamadas == []


def test_error_transporte_consulta_503():
    def caida(r): raise httpx.ConnectError("caída simulada", request=r)
    servicio = ClienteReentrenamientos("http://airflow.simulado", "pruebas", "clave-sintetica",
                                       transporte=httpx.MockTransport(caida))
    app = crear_app()
    app.dependency_overrides[obtener_reentrenamientos] = lambda: servicio
    with TestClient(app) as cliente:
        assert cliente.get("/admin/reentrenar/conocido").status_code == 503
