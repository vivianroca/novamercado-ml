"""Compatibilidad HTTP/Registry exclusivamente en el servidor de pytest."""

import hashlib
import json
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest


@pytest.fixture
def cliente_mlflow(entorno_mlflow):
    return entorno_mlflow.cliente


def test_mlflow_3172_conserva_runs_y_artefactos(cliente_mlflow, entorno_mlflow):
    inventario = entorno_mlflow.inventario
    cliente = cliente_mlflow
    for experimento in inventario["experimentos"]:
        actual = cliente.get_experiment(experimento["id"])
        assert actual.name == experimento["nombre"]
        assert actual.lifecycle_stage == experimento["estado"]
    for identificador, previo in inventario["runs"].items():
        actual = cliente.get_run(identificador)
        assert actual.info.status == previo["estado"]
        assert actual.info.lifecycle_stage == previo["lifecycle_stage"]
        assert actual.data.params == previo["params"]
        assert actual.data.metrics == previo["metricas"]
        assert all(actual.data.tags.get(k) == v for k, v in previo["tags"].items())
        entradas = {i.dataset.name: i.dataset.digest for i in actual.inputs.dataset_inputs}
        assert entradas == {i["dataset"]["name"]: i["dataset"]["digest"]
                            for i in previo["inputs"].get("dataset_inputs", [])}
        for ruta, digest in previo["artefactos"].items():
            with tempfile.TemporaryDirectory() as temporal:
                archivo = Path(cliente.download_artifacts(identificador, ruta, temporal))
                assert hashlib.sha256(archivo.read_bytes()).hexdigest() == digest


def test_mlflow_3172_registry_y_aliases(cliente_mlflow, entorno_mlflow):
    cliente = cliente_mlflow
    # Solo metadata temporal de compatibilidad, no un modelo entrenado o promovido.
    nombre = "compatibilidad_temporal_" + uuid4().hex
    run_id = entorno_mlflow.baseline_run_id
    fuente = cliente.get_run(run_id).info.artifact_uri + "/baseline"
    cliente.create_registered_model(nombre, tags={"proposito": "prueba_compatibilidad"})
    v1 = cliente.create_model_version(nombre, fuente, run_id=run_id)
    v2 = cliente.create_model_version(nombre, fuente, run_id=run_id)
    assert cliente.get_model_version(nombre, v1.version).run_id == run_id
    cliente.set_registered_model_alias(nombre, "compatibilidad", v1.version)
    assert cliente.get_model_version_by_alias(nombre, "compatibilidad").version == v1.version
    cliente.set_registered_model_alias(nombre, "compatibilidad", v2.version)
    assert cliente.get_model_version_by_alias(nombre, "compatibilidad").version == v2.version
    # Todo queda en el store aislado; no se elimina ningún modelo o run.


def test_mlflow_3172_tracking_existente(cliente_mlflow, entorno_mlflow):
    from ml.tracking import registrar_baseline
    identificador = registrar_baseline(entorno_mlflow.ruta_reporte, entorno_mlflow.datos, cliente=cliente_mlflow)
    run = cliente_mlflow.get_run(identificador)
    assert run.info.status == "FINISHED"
    assert cliente_mlflow.get_experiment(run.info.experiment_id).name == "NovaMercado"
    assert run.data.metrics["costo_total"] == entorno_mlflow.reporte["metricas"]["costo_total"]
    assert len(run.data.metrics) == 14
    assert len(run.inputs.dataset_inputs) == 4
    with tempfile.TemporaryDirectory() as temporal:
        ruta = Path(cliente_mlflow.download_artifacts(identificador, "evaluacion/reporte.json", temporal))
        assert json.loads(ruta.read_text()) == entorno_mlflow.reporte


def test_mlflow_3172_host_interno_y_ui(cliente_mlflow, entorno_mlflow):
    uri = entorno_mlflow.uri
    with urlopen(Request(uri + "/version", headers={"Host": "mlflow:5000"}), timeout=10) as r:
        assert r.read().decode().strip() == "3.17.2"
    with urlopen(uri + "/", timeout=10) as r:
        assert r.status == 200
