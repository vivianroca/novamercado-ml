"""Tracking de pytest aislado, incluso si el shell apunta a producción."""

import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.request import urlopen

import pytest


@pytest.fixture(autouse=True)
def aislamiento_mlflow(tmp_path, monkeypatch):
    import mlflow

    uri = "sqlite:///" + str(tmp_path / "tracking.db")
    permitidos = {uri}
    anterior, registry_anterior = mlflow.get_tracking_uri(), mlflow.get_registry_uri()
    for clave in ("MLFLOW_TRACKING_URI", "MLFLOW_REGISTRY_URI", "TEST_MLFLOW_TRACKING_URI"):
        monkeypatch.setenv(clave, uri)
    for clave in ("MLFLOW_RUN_ID", "MLFLOW_EXPERIMENT_ID", "MLFLOW_EXPERIMENT_NAME", "TEST_MLFLOW_INVENTARIO"):
        monkeypatch.delenv(clave, raising=False)
    mlflow.set_tracking_uri(uri)
    mlflow.set_registry_uri(uri)
    original = mlflow.MlflowClient.__init__

    def cliente_seguro(self, tracking_uri=None, registry_uri=None, *args, **kwargs):
        tracking = str(tracking_uri or mlflow.get_tracking_uri())
        registry = str(registry_uri or mlflow.get_registry_uri())
        if tracking not in permitidos or registry not in permitidos:
            raise RuntimeError("pytest solo permite tracking y Registry aislados; conexión externa bloqueada")
        original(self, tracking_uri=tracking, registry_uri=registry, *args, **kwargs)

    monkeypatch.setattr(mlflow.MlflowClient, "__init__", cliente_seguro)
    try:
        yield permitidos
    finally:
        mlflow.set_tracking_uri(anterior)
        mlflow.set_registry_uri(registry_anterior)


@pytest.fixture(scope="session")
def servidor_mlflow(tmp_path_factory):
    """Servidor local efímero, sin Docker, volúmenes ni datos del servicio principal."""
    raiz = tmp_path_factory.mktemp("mlflow-aislado")
    with socket.socket() as socket_libre:
        socket_libre.bind(("127.0.0.1", 0))
        puerto = socket_libre.getsockname()[1]
    uri = f"http://127.0.0.1:{puerto}"
    entorno = {k: v for k, v in os.environ.items() if not k.startswith(("MLFLOW_", "TEST_MLFLOW_"))}
    entorno["MLFLOW_DISABLE_AGENT_HINT"] = "1"
    with (raiz / "servidor.log").open("w") as log:
        proceso = subprocess.Popen([
            sys.executable, "-m", "mlflow", "server", "--host", "127.0.0.1", "--port", str(puerto),
            "--workers", "1", "--backend-store-uri", "sqlite:///" + str(raiz / "metadata.db"),
            "--serve-artifacts", "--artifacts-destination", str(raiz / "artefactos"),
            "--allowed-hosts", f"127.0.0.1:{puerto},localhost:{puerto},mlflow:5000",
        ], cwd=raiz, env=entorno, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            limite = time.monotonic() + 60
            while True:
                if proceso.poll() is not None:
                    pytest.fail("MLflow de pruebas no arrancó: " + (raiz / "servidor.log").read_text()[-4000:])
                try:
                    with urlopen(uri + "/health", timeout=1) as respuesta:
                        if respuesta.status == 200:
                            break
                except OSError:
                    pass
                if time.monotonic() >= limite:
                    pytest.fail("Tiempo agotado al iniciar MLflow aislado")
                time.sleep(0.2)
            yield _preparar_servidor(uri, raiz)
        finally:
            if proceso.poll() is None:
                os.killpg(proceso.pid, signal.SIGTERM)
                try:
                    proceso.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(proceso.pid, signal.SIGKILL)
                    proceso.wait(timeout=5)
            # No borrar runs, modelos, bases, artefactos ni volúmenes.


def _preparar_servidor(uri, raiz):
    """Insumos sintéticos propios, sin leer GES ni IDs del producto."""
    import mlflow
    from ml.tracking import INSUMOS, registrar_baseline, sha256

    anterior, registry_anterior = mlflow.get_tracking_uri(), mlflow.get_registry_uri()
    mlflow.set_tracking_uri(uri)
    mlflow.set_registry_uri(uri)
    try:
        cliente = mlflow.MlflowClient(tracking_uri=uri, registry_uri=uri)
        datos = raiz / "datos"
        datos.mkdir()
        for nombre in INSUMOS:
            (datos / nombre).write_text("insumo_sintetico\n")
        metricas = {"registros": 2, "mae": 10.0, "rmse": 12.0, "wape": 0.2,
                    "costo_total": 100.0, "costo_medio": 50.0, "costo_sugerido_media": 110.0}
        reporte = {"baseline": "media_semanal_cuantil_empirico", "ventana_dias": 56,
            "inicio": "2026-01-04", "fin": "2026-02-28", "entrenamiento_hasta": "2026-01-03",
            "protocolo": "sintetico_pruebas", "metricas": metricas, "por_familia": {"pan": metricas},
            "sha256_insumos": {n: sha256(datos / n) for n in INSUMOS}}
        ruta = raiz / "reporte.json"
        ruta.write_text(json.dumps(reporte))
        baseline_run_id = registrar_baseline(ruta, datos, cliente=cliente)
        experimento = cliente.get_experiment_by_name("NovaMercado")
        modelo_run = cliente.create_run(experimento.experiment_id, tags={"mlflow.runName": "pytest-modelo-sintetico"})
        candidato = {"inicio": reporte["inicio"], "fin": reporte["fin"],
            "ajuste_hasta": "2025-12-06", "calibracion_inicio": "2025-12-07", "calibracion_fin": "2026-01-03",
            "metricas": {**metricas, "costo_total": 90.0, "costo_medio": 45.0},
            "por_familia": {"pan": {**metricas, "costo_total": 90.0, "costo_medio": 45.0}},
            "sha256_insumos": reporte["sha256_insumos"], "baseline": reporte}
        cliente.log_dict(modelo_run.info.run_id, candidato, "evaluacion/comparacion.json")
        for k, v in candidato["metricas"].items():
            cliente.log_metric(modelo_run.info.run_id, k, v)
        cliente.set_terminated(modelo_run.info.run_id, status="FINISHED")
        modelo_nombre = "pytest-histgradientboosting"
        cliente.create_registered_model(modelo_nombre)
        version = cliente.create_model_version(modelo_nombre, modelo_run.info.artifact_uri, run_id=modelo_run.info.run_id)
        cliente.set_registered_model_alias(modelo_nombre, "champion", version.version)
        inventario = {"experimentos": [{"id": experimento.experiment_id, "nombre": experimento.name,
                                       "estado": experimento.lifecycle_stage}], "runs": {}}
        for identificador in (baseline_run_id, modelo_run.info.run_id):
            run = cliente.get_run(identificador)
            artefactos = {}
            def visitar(ruta=None):
                for a in cliente.list_artifacts(identificador, ruta):
                    if a.is_dir:
                        visitar(a.path)
                    else:
                        archivo = Path(cliente.download_artifacts(identificador, a.path, str(raiz)))
                        artefactos[a.path] = hashlib.sha256(archivo.read_bytes()).hexdigest()
            visitar()
            inventario["runs"][identificador] = {"estado": run.info.status,
                "lifecycle_stage": run.info.lifecycle_stage, "params": run.data.params,
                "metricas": run.data.metrics, "tags": run.data.tags,
                "inputs": run.inputs.to_dictionary(), "artefactos": artefactos}
        return SimpleNamespace(uri=uri, cliente=cliente, raiz=raiz, reporte=reporte, datos=datos,
            ruta_reporte=ruta, baseline_run_id=baseline_run_id, modelo_nombre=modelo_nombre,
            version=version.version, inventario=inventario)
    finally:
        mlflow.set_tracking_uri(anterior)
        mlflow.set_registry_uri(registry_anterior)


@pytest.fixture
def entorno_mlflow(servidor_mlflow, aislamiento_mlflow, monkeypatch):
    import mlflow
    aislamiento_mlflow.add(servidor_mlflow.uri)
    for clave in ("MLFLOW_TRACKING_URI", "MLFLOW_REGISTRY_URI", "TEST_MLFLOW_TRACKING_URI"):
        monkeypatch.setenv(clave, servidor_mlflow.uri)
    mlflow.set_tracking_uri(servidor_mlflow.uri)
    mlflow.set_registry_uri(servidor_mlflow.uri)
    return servidor_mlflow


@pytest.fixture
def modelo_serving(entorno_mlflow, tmp_path, monkeypatch):
    """HGB ejecutable real, entrenado solo con datos sintéticos en el store aislado."""
    import csv
    from datetime import date, timedelta
    from uuid import uuid4
    import joblib
    import mlflow
    import pandas as pd
    from mlflow.models import infer_signature
    from ml.baseline import Costos
    from ml.features import construir_matriz, NOMBRES
    from ml.histgradient import evaluar_histgradient
    from ml.modelo_inventario import InventarioHGB

    datos = tmp_path / "datos_serving"
    datos.mkdir()
    (datos / "tiendas.csv").write_text("tienda_id,nombre,ciudad,departamento,tipo,fecha_apertura\n5,Prueba,Guatemala,Guatemala,express,2024-01-01\n")
    (datos / "familias.csv").write_text("familia_id,nombre\npan,Pan\n")
    (datos / "costos.csv").write_text("familia_id,costo_faltante,costo_sobrante\npan,1,2\n")
    (datos / "feriados.csv").write_text("fecha,nombre,tipo,ambito\n2026-01-01,Año nuevo,feriado,nacional\n")
    with (datos / "historico_ventas.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["fecha", "tienda_id", "familia_id", "ventas", "en_promocion"])
        for i in range(100):
            w.writerow([(date(2025, 10, 1) + timedelta(days=i)).isoformat(), 5, "pan", 20 + i % 7 * 5 + i % 3 * 10, i % 3])
    x, ventas, contexto = construir_matriz(datos)
    estimador, reporte, _ = evaluar_histgradient(x, ventas, {"pan": Costos(1, 2)},
        date(2026, 1, 4), date(2026, 1, 8), parametros={"max_iter": 5, "min_samples_leaf": 2})
    bundle = {"estimador": estimador, "features": NOMBRES,
              "ajustes_codificados": {0: reporte["ajustes_por_familia"]["pan"]}}
    ruta = tmp_path / "bundle.joblib"
    joblib.dump(bundle, ruta)
    ejemplo = pd.DataFrame(x[-1:], columns=NOMBRES)
    envuelto = InventarioHGB()
    envuelto.bundle = bundle
    metadata = {"features": NOMBRES, "familias": contexto.familias, "tiendas": sorted(contexto.tiendas),
                "ciudades": contexto.ciudades, "formatos": contexto.formatos}
    nombre = "pytest-serving-" + uuid4().hex
    mlflow.set_experiment("NovaMercado")
    with mlflow.start_run(run_name="pytest-serving-sintetico"):
        mlflow.log_dict(metadata, "configuracion/features_y_sugeridos.json")
        mlflow.log_dict(reporte, "evaluacion/comparacion.json")
        info = mlflow.pyfunc.log_model(name="modelo", python_model=InventarioHGB(),
            artifacts={"bundle": str(ruta)}, registered_model_name=nombre,
            signature=infer_signature(ejemplo, envuelto.predict(None, ejemplo)),
            pip_requirements=str(Path(__file__).resolve().parents[1] / "requirements.txt"))
    entorno_mlflow.cliente.set_registered_model_alias(nombre, "champion", info.registered_model_version)
    monkeypatch.setenv("DATA_DIR", str(datos))
    monkeypatch.setenv("MODEL_NAME", nombre)
    monkeypatch.setenv("MODEL_CACHE_DIR", str(tmp_path / "cache_modelos"))
    monkeypatch.setenv("MODEL_REFRESH_SECONDS", "60")
    return SimpleNamespace(nombre=nombre, version=str(info.registered_model_version),
                           modelo=envuelto, metadata=metadata, data_dir=datos, uri=entorno_mlflow.uri)
