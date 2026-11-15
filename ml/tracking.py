"""Registra una evaluación existente; no entrena ni promueve modelos."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess

EXPERIMENTO = "NovaMercado"
INSUMOS = ("historico_ventas.csv", "costos.csv", "tiendas.csv", "familias.csv")
RAIZ = Path(__file__).resolve().parents[1]


def sha256(ruta):
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def preparar_registro(reporte, data_dir):
    ruta = Path(reporte)
    evaluacion = json.loads(ruta.read_text())
    if evaluacion.get("baseline") != "media_semanal_cuantil_empirico":
        raise ValueError("Solo se admite el baseline existente")
    hashes = {nombre: sha256(Path(data_dir) / nombre) for nombre in INSUMOS}
    if evaluacion.get("sha256_insumos") != hashes:
        raise ValueError("Los hashes del reporte no coinciden con los insumos")
    if not evaluacion["entrenamiento_hasta"] < evaluacion["inicio"] <= evaluacion["fin"]:
        raise ValueError("Cortes temporales inválidos")
    metricas = {}
    for prefijo, valores in [("", evaluacion["metricas"])] + [
        (f"familia/{familia}/", m) for familia, m in evaluacion["por_familia"].items()
    ]:
        for nombre, valor in valores.items():
            if valor is None:  # WAPE indefinido se conserva como null en el artefacto.
                continue
            if type(valor) not in (float, int) or not math.isfinite(valor):
                raise ValueError("Métrica no numérica o no finita")
            metricas[prefijo + nombre] = valor
    codigos = ["ml/baseline.py", "ml/datos.py", "ml/evaluacion.py", "ml/tracking.py", "requirements.txt"]
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=RAIZ, text=True).strip()
    linaje = {
        "sha256_insumos": hashes, "sha256_reporte": sha256(ruta),
        "codigo_al_registrar": {nombre: sha256(RAIZ / nombre) for nombre in codigos},
        "git_commit_al_registrar": git("rev-parse", "HEAD"),
        "git_modificado_al_registrar": bool(git("status", "--porcelain")),
        "python": platform.python_version(),
        "operacion": "registro_de_evaluacion_preexistente_sin_entrenamiento",
    }
    parametros = {k: evaluacion[k] for k in ["baseline", "ventana_dias", "inicio", "fin", "entrenamiento_hasta", "protocolo"]}
    parametros.update({"sugerido": "cuantil_empirico_costos", "promociones": "no_utilizadas",
                       "feriados": "no_utilizados"})
    return evaluacion, parametros, metricas, linaje, codigos


def registrar_baseline(reporte, data_dir="data", tracking_uri=None, cliente=None):
    # Ninguna conexión ni escritura si el reporte o los hashes no son válidos.
    evaluacion, parametros, metricas, linaje, codigos = preparar_registro(reporte, data_dir)
    from mlflow import MlflowClient, set_tracking_uri
    from mlflow.entities import Dataset, DatasetInput, InputTag
    from mlflow.exceptions import MlflowException

    if cliente is None:
        uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI")
        if not uri or not uri.startswith(("http://", "https://")):
            raise ValueError("Configurar MLFLOW_TRACKING_URI HTTP del servicio Compose mlflow")
        # mlflow-artifacts:/ requiere alinear también el URI global al servidor.
        set_tracking_uri(uri)
        cliente = MlflowClient(tracking_uri=uri)
    experimento = cliente.get_experiment_by_name(EXPERIMENTO)
    if experimento is None:
        try:
            identificador = cliente.create_experiment(EXPERIMENTO)
        except MlflowException as error:
            # Carrera entre registradores: reutilizar solo si ya existe.
            experimento = cliente.get_experiment_by_name(EXPERIMENTO)
            if experimento is None:
                raise error
            identificador = experimento.experiment_id
    else:
        identificador = experimento.experiment_id
    run = cliente.create_run(identificador, tags={
        "mlflow.runName": "baseline-semanal", "novamercado.tipo": "baseline",
        "novamercado.operacion": "registro_sin_entrenamiento",
        "novamercado.reporte_sha256": linaje["sha256_reporte"],
        "mlflow.source.git.commit": linaje["git_commit_al_registrar"],
    })
    run_id = run.info.run_id
    try:
        for nombre, valor in parametros.items():
            cliente.log_param(run_id, nombre, valor)
        for nombre, valor in metricas.items():
            cliente.log_metric(run_id, nombre, valor)
        cliente.log_dict(run_id, evaluacion, "evaluacion/reporte.json")
        cliente.log_dict(run_id, linaje, "linaje/manifest.json")
        cliente.log_dict(run_id, parametros, "baseline/configuracion.json")
        for nombre in codigos:
            destino = (Path("codigo") / Path(nombre).parent).as_posix()
            cliente.log_artifact(run_id, str(RAIZ / nombre), destino)
        cliente.log_inputs(run_id, [DatasetInput(
            Dataset(name=nombre, digest=digest[:32], source_type="local",
                    source=json.dumps({"uri": nombre})),
            tags=[InputTag("mlflow.data.context", "historico_entrenamiento_y_validacion" if nombre == "historico_ventas.csv" else "referencia")],
        ) for nombre, digest in linaje["sha256_insumos"].items()])
        cliente.set_terminated(run_id, status="FINISHED")
    except Exception:
        cliente.set_terminated(run_id, status="FAILED")
        raise
    return run_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reporte", default="evidencias/baseline_4_1.json")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--tracking-uri", default=None)
    args = parser.parse_args()
    print(json.dumps({"experimento": EXPERIMENTO, "run_id": registrar_baseline(
        args.reporte, args.data_dir, args.tracking_uri)}))


if __name__ == "__main__":
    main()
