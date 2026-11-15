"""DAG manual Airflow 3.3.2. Solo stdlib y SDK durante el parseo."""

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlencode
from urllib.request import urlopen

from airflow.sdk import dag, task, get_current_context


def version_champion():
    uri = os.environ["MLFLOW_TRACKING_URI"].rstrip("/")
    parametros = urlencode({"name": os.environ.get("MODEL_NAME", "novamercado-histgradientboosting"), "alias": "champion"})
    with urlopen(uri + "/api/2.0/mlflow/registered-models/get-by-alias?" + parametros, timeout=3) as respuesta:
        version = json.loads(respuesta.read())["model_version"]["version"]
    if not isinstance(version, str) or not version:
        raise ValueError("Registry no confirmó una versión vigente")
    return version


def resultado_final(decision):
    # La decisión ya captura la versión vigente al acabar la promoción.
    # Un único escritor impide otra promoción hasta cerrar este DAG.
    if (isinstance(decision, dict) and decision.get("estado") in ("exitoso", "fallido")
            and type(decision.get("promovido")) is bool and isinstance(decision.get("version"), str)
            and decision["version"] and isinstance(decision.get("motivo"), str) and decision["motivo"]):
        return {k: decision[k] for k in ("estado", "promovido", "version", "motivo")}
    try:
        version = version_champion()  # Solo lectura, para fallos previos a la decisión.
    except Exception:
        version = None  # Nunca inventar versión si no se puede confirmar.
    return {"estado": "fallido", "promovido": False, "version": version,
            "motivo": "Falló el entrenamiento/evaluación o no se completó una decisión verificable"}


def invocar(modo, run_id, conf, manifiesto=None):
    if set(conf) - {"fecha_fin"}:
        raise ValueError("Configuración desconocida: solo se admite fecha_fin simulada")
    raiz = Path(os.environ.get("NOVAMERCADO_ROOT", "/opt/novamercado"))
    trabajo = Path(os.environ.get("RETRAIN_WORK_DIR", "/opt/airflow/work")) / hashlib.sha256(run_id.encode()).hexdigest()
    trabajo.mkdir(parents=True, exist_ok=True)
    salida = trabajo / ("entrenamiento.json" if modo == "entrenar" else "decision.json")
    comando = [os.environ.get("NOVAMERCADO_PYTHON", "/opt/novamercado/.venv/bin/python"),
               "-m", "ml.reentrenamiento", modo, "--run-id", run_id, "--salida", str(salida)]
    if conf.get("fecha_fin") is not None:
        # Formato estricto antes de lanzar trabajo; no se usa el reloj real.
        fecha = date.fromisoformat(conf["fecha_fin"]).isoformat()
        comando.extend(["--fecha-fin", fecha])
    if manifiesto is not None:
        comando.extend(["--manifesto", manifiesto])
    subprocess.run(comando, cwd=raiz, check=True, timeout=480 if modo == "entrenar" else 75)
    if modo == "entrenar":
        reporte = json.loads(salida.read_text())
        return {"manifesto": str(salida), "version": reporte["mlflow"]["version"],
                "run_id": reporte["mlflow"]["run_id"]}
    return json.loads(salida.read_text())


@dag(dag_id="novamercado_reentrenamiento", start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
     schedule=None, catchup=False, max_active_runs=1, dagrun_timeout=timedelta(minutes=10),
     tags=["novamercado", "mlflow"], default_args={"retries": 0})
def crear_dag():
    @task(task_id="entrenar_y_evaluar", execution_timeout=timedelta(minutes=8, seconds=15))
    def entrenar():
        contexto = get_current_context()
        return invocar("entrenar", contexto["run_id"], contexto["dag_run"].conf or {})

    @task(task_id="decidir_champion", execution_timeout=timedelta(seconds=90))
    def promover(resultado):
        contexto = get_current_context()
        return invocar("promover", contexto["run_id"], contexto["dag_run"].conf or {}, resultado["manifesto"])

    @task(task_id="finalizar_reentrenamiento", trigger_rule="all_done", execution_timeout=timedelta(seconds=10))
    def finalizar():
        contexto = get_current_context()
        ti = contexto["ti"]
        decision = ti.xcom_pull(task_ids="decidir_champion", key="return_value")
        resultado = resultado_final(decision)
        ti.xcom_push(key="resultado_reentrenamiento", value=resultado)
        if resultado["estado"] == "fallido":
            # all_done no debe convertir un fallo previo en DagRun success.
            raise RuntimeError(resultado["motivo"])
        return resultado

    promover(entrenar()) >> finalizar()


dag = crear_dag()
