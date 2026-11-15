"""Comprobación con Airflow real en metastore temporal; nunca en el producto."""

import argparse
import json
import os
from pathlib import Path
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ejecutar", action="store_true")
    parser.add_argument("--esperar-fallo", action="store_true")
    parser.add_argument("--salida", required=True)
    args = parser.parse_args()
    raiz = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="novamercado-airflow-test-") as temporal:
        os.environ.update({"AIRFLOW_HOME": temporal, "AIRFLOW__CORE__LOAD_EXAMPLES": "false",
            "AIRFLOW__CORE__DAGS_FOLDER": str(raiz / "airflow/dags"),
            "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN": "sqlite:///" + str(Path(temporal) / "metadata.db"),
            "AIRFLOW__CORE__EXECUTOR": "LocalExecutor", "AIRFLOW__CORE__UNIT_TEST_MODE": "True"})
        import airflow
        from airflow.models import DagBag
        from airflow.serialization.serialized_objects import DagSerialization
        bag = DagBag(dag_folder=str(raiz / "airflow/dags"))
        assert not bag.import_errors, bag.import_errors
        dag = bag.dags["novamercado_reentrenamiento"]
        assert set(dag.task_ids) == {"entrenar_y_evaluar", "decidir_champion", "finalizar_reentrenamiento"}
        assert dag.get_task("entrenar_y_evaluar").downstream_task_ids == {"decidir_champion"}
        assert dag.max_active_runs == 1 and dag.catchup is False
        assert dag.dagrun_timeout.total_seconds() == 600
        assert all(t.retries == 0 for t in dag.tasks)
        regla = dag.get_task("finalizar_reentrenamiento").trigger_rule
        assert getattr(regla, "value", regla) == "all_done"
        DagSerialization.to_dict(dag)
        resultado = {"airflow": airflow.__version__, "dag": dag.dag_id, "tareas": sorted(dag.task_ids),
                     "parseo_y_serializacion": "ok"}
        # Simulación del cierre: nunca dispara tareas de entrenamiento ni Registry real.
        import sys
        funcion = dag.get_task("finalizar_reentrenamiento").python_callable
        modulo = sys.modules[funcion.__module__]
        contexto_original, version_original = modulo.get_current_context, modulo.version_champion
        from types import SimpleNamespace
        guardado = {}
        def guardar(key, value): guardado[key] = value
        def version_simulada(): return "7"
        try:
            modulo.version_champion = version_simulada
            ti = SimpleNamespace(xcom_pull=lambda **kw: {"estado": "exitoso", "promovido": False,
                "version": "6", "motivo": "Costo sin mejora"}, xcom_push=guardar)
            modulo.get_current_context = lambda: {"ti": ti, "run_id": "simulado"}
            assert funcion()["version"] == "6"  # No sustituir por el champion actual (7).
            ti.xcom_pull = lambda **kw: None
            try:
                funcion()
                raise AssertionError("El finalizador ocultó el fallo del DAG")
            except RuntimeError:
                assert guardado["resultado_reentrenamiento"]["estado"] == "fallido"
                assert guardado["resultado_reentrenamiento"]["version"] == "7"
            def caida(): raise ConnectionError("simulado")
            modulo.version_champion = caida
            assert modulo.resultado_final(None)["version"] is None
            resultado["finalizador_simulado"] = "ok"
        finally:
            modulo.get_current_context, modulo.version_champion = contexto_original, version_original
        if args.ejecutar:
            uri = os.environ.get("MLFLOW_TRACKING_URI", "")
            assert os.environ.get("NOVAMERCADO_PRUEBA_AISLADA") == "1"
            assert uri.startswith("http://127.0.0.1:") and uri != "http://127.0.0.1:5001"
            assert os.environ.get("PRODUCT_DB_NAME", "").startswith("test_novamercado_")
            from airflow.utils import db
            from datetime import datetime, timezone
            db.initdb()
            run = dag.test(logical_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
                           run_conf={"fecha_fin": "2026-03-15"})
            resultado["estado"] = str(run.state)
            resultado["estados_tareas"] = {t.task_id: str(t.state) for t in run.get_task_instances()}
            if args.esperar_fallo:
                assert run.state == "failed", resultado
                assert resultado["estados_tareas"]["entrenar_y_evaluar"] == "failed"
                assert resultado["estados_tareas"]["decidir_champion"] in ("upstream_failed", "skipped")
            else:
                assert run.state == "success", resultado
        Path(args.salida).write_text(json.dumps(resultado, indent=2) + "\n")
        print(json.dumps(resultado))


if __name__ == "__main__":
    main()
