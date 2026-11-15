"""Entrenamiento manual, registro y política champion. Sin Airflow."""

import argparse
from datetime import date
import json
from pathlib import Path
import platform
import tempfile

import joblib
import mlflow
from mlflow.entities import Dataset, DatasetInput, InputTag
from mlflow.models import infer_signature
import pandas as pd
import sklearn

from ml.datos import cargar_datos
from ml.features import construir_matriz, NOMBRES
from ml.histgradient import evaluar_histgradient, evaluar_modelo_congelado
from ml.modelo_inventario import InventarioHGB
from ml.promocion import evaluar_champion, ReferenciaEvaluada, _reporte
from ml.tracking import EXPERIMENTO, INSUMOS, RAIZ, sha256, proveniencia_git


def entrenar_y_registrar(data_dir, inicio, fin, tracking_uri, salida, *, promover=True,
                        nombre_modelo="novamercado-histgradientboosting", linaje_extra=None):
    historial, costos = cargar_datos(data_dir)
    x, ventas, contexto = construir_matriz(data_dir)
    if {(v.fecha, v.tienda_id, v.familia_id) for v in historial} != {(v.fecha, v.tienda_id, v.familia_id) for v in ventas}:
        raise ValueError("Insumos de evaluación y features distintos")
    modelo, reporte, filas = evaluar_histgradient(x, ventas, costos, inicio, fin)
    hashes = {nombre: sha256(Path(data_dir) / nombre) for nombre in (*INSUMOS, "feriados.csv")}
    reporte["sha256_insumos"] = hashes
    codigos = ["ml/features.py", "ml/histgradient.py", "ml/modelo_inventario.py", "ml/entrenamiento.py",
               "ml/baseline.py", "ml/evaluacion.py", "ml/datos.py", "ml/promocion.py", "requirements.txt"]
    commit, dirty = proveniencia_git()
    linaje = {"sha256_insumos": hashes, "sha256_codigo": {c: sha256(RAIZ / c) for c in codigos},
        "git_commit": commit, "git_modificado": dirty,
        "python": platform.python_version(), "sklearn": sklearn.__version__, "mlflow": mlflow.__version__,
        "ajuste_hasta": reporte["ajuste_hasta"], "calibracion_fin": reporte["calibracion_fin"],
        "validacion_inicio": reporte["inicio"], "validacion_fin": reporte["fin"]}
    if linaje_extra:
        linaje["snapshot_producto"] = linaje_extra
    bundle = {"estimador": modelo, "features": NOMBRES,
        "ajustes_codificados": {contexto.familias[f]: a for f, a in reporte["ajustes_por_familia"].items()}}
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_registry_uri(tracking_uri)
    mlflow.set_experiment(EXPERIMENTO)
    with mlflow.start_run(run_name="histgradientboosting-calendario-rezagos") as run:
        mlflow.set_tags({k: v for k, v in {"novamercado.tipo": "candidato",
                         "mlflow.source.git.commit": linaje["git_commit"]}.items() if v is not None})
        if linaje_extra and linaje_extra.get("airflow_run_id"):
            mlflow.set_tag("novamercado.airflow_run_id", linaje_extra["airflow_run_id"])
        mlflow.log_params({**reporte["parametros"], "inicio_validacion": reporte["inicio"],
            "fin_validacion": reporte["fin"], "ajuste_hasta": reporte["ajuste_hasta"],
            "calibracion_inicio": reporte["calibracion_inicio"], "calibracion_fin": reporte["calibracion_fin"],
            "filas_ajuste": reporte["filas_ajuste"], "filas_calibracion": reporte["filas_calibracion"],
            "features": len(NOMBRES), "sugerido": "prediccion_mas_cuantil_residual_por_familia",
            "hilos": 2})
        for prefijo, valores in [("", reporte["metricas"])] + [
            (f"familia/{f}/", m) for f, m in reporte["por_familia"].items()
        ]:
            mlflow.log_metrics({prefijo + k: v for k, v in valores.items() if v is not None})
        mlflow.log_metric("segundos_ajuste_evaluacion", reporte["segundos_ajuste_evaluacion"])
        mlflow.log_dict(reporte, "evaluacion/comparacion.json")
        mlflow.log_dict(linaje, "linaje/manifest.json")
        mlflow.log_dict({"features": NOMBRES, "familias": contexto.familias,
            "tiendas": sorted(contexto.tiendas), "ciudades": contexto.ciudades, "formatos": contexto.formatos,
            "ajustes_por_familia": reporte["ajustes_por_familia"]}, "configuracion/features_y_sugeridos.json")
        for codigo in codigos:
            mlflow.log_artifact(str(RAIZ / codigo), (Path("codigo") / Path(codigo).parent).as_posix())
        cliente = mlflow.MlflowClient()
        cliente.log_inputs(run.info.run_id, [DatasetInput(
            Dataset(name=nombre, digest=digest[:32], source_type="local", source=json.dumps({"uri": nombre})),
            tags=[InputTag("mlflow.data.context", "ajuste_calibracion_validacion" if nombre == "historico_ventas.csv" else "referencia")])
            for nombre, digest in hashes.items()])
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "inventario.joblib"
            joblib.dump(bundle, ruta)
            ejemplo = pd.DataFrame(x[-1:], columns=NOMBRES)
            envoltura = InventarioHGB()
            envoltura.bundle = bundle
            signature = infer_signature(ejemplo, envoltura.predict(None, ejemplo))
            info = mlflow.pyfunc.log_model(
                name="histgradientboosting", python_model=InventarioHGB(),
                artifacts={"bundle": str(ruta)}, code_paths=[str(RAIZ / "ml")],
                signature=signature, pip_requirements=str(RAIZ / "requirements.txt"),
                registered_model_name=nombre_modelo,
            )
        # Verificar round-trip del modelo real guardado, sin tocar alias alguno.
        cargado = mlflow.pyfunc.load_model(info.model_uri)
        esperado = envoltura.predict(None, ejemplo)
        pd.testing.assert_frame_equal(cargado.predict(ejemplo), esperado)
        reporte["mlflow"] = {"run_id": run.info.run_id, "experimento": EXPERIMENTO,
                             "model_uri": info.model_uri, "version": str(info.registered_model_version)}
    # Evaluar solo después de confirmar que terminó el run del candidato.
    cliente = mlflow.MlflowClient()
    referencia = None
    vigente = cliente.get_registered_model(nombre_modelo).aliases.get("champion")
    if vigente:
        try:
            origen = _reporte(cliente, nombre_modelo, vigente)
            with tempfile.TemporaryDirectory() as t:
                v = cliente.get_model_version(nombre_modelo, vigente)
                meta = json.loads(Path(cliente.download_artifacts(v.run_id, "configuracion/features_y_sugeridos.json", t)).read_text())
            esperado = {"features": NOMBRES, "familias": contexto.familias, "tiendas": sorted(contexto.tiendas),
                        "ciudades": contexto.ciudades, "formatos": contexto.formatos}
            if any(meta.get(k) != valor for k, valor in esperado.items()):
                raise ValueError("Codificación de variables del champion incompatible")
            congelado = mlflow.pyfunc.load_model(f"models:/{nombre_modelo}/{vigente}")
            referencia = ReferenciaEvaluada(str(vigente), evaluar_modelo_congelado(
                congelado, x, ventas, costos, origen, reporte))
        except Exception as error:
            referencia = ReferenciaEvaluada(str(vigente), error=f"No se pudo reevaluar champion: {type(error).__name__}: {error}")
    reporte["referencia_champion"] = vars(referencia) if referencia else None
    if promover:
        reporte["decision_champion"] = evaluar_champion(cliente, nombre_modelo, reporte["mlflow"]["version"], referencia)
    Path(salida).parent.mkdir(parents=True, exist_ok=True)
    Path(salida).write_text(json.dumps(reporte, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return reporte


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--inicio", type=date.fromisoformat, default=date(2026, 1, 4))
    parser.add_argument("--fin", type=date.fromisoformat, default=date(2026, 2, 28))
    parser.add_argument("--tracking-uri", default="http://127.0.0.1:5001")
    parser.add_argument("--salida", default="evidencias/comparacion_histgradient.json")
    args = parser.parse_args()
    r = entrenar_y_registrar(args.data_dir, args.inicio, args.fin, args.tracking_uri, args.salida)
    print(json.dumps({"baseline": r["baseline"]["metricas"], "histgradientboosting": r["metricas"],
                      "mlflow": r["mlflow"], "decision_champion": r["decision_champion"]}, indent=2))


if __name__ == "__main__":
    main()
