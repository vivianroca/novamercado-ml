import os

import mlflow
import pytest


def test_tracking_y_registry_por_defecto_son_temporales(tmp_path):
    esperado = "sqlite:///" + str(tmp_path / "tracking.db")
    assert mlflow.get_tracking_uri() == mlflow.get_registry_uri() == esperado
    assert os.environ["TEST_MLFLOW_TRACKING_URI"] == esperado
    assert "MLFLOW_RUN_ID" not in os.environ


@pytest.mark.parametrize("argumento", ["tracking_uri", "registry_uri"])
def test_cliente_externo_bloqueado_antes_de_conectar(argumento):
    with pytest.raises(RuntimeError, match="conexión externa bloqueada"):
        mlflow.MlflowClient(**{argumento: "http://127.0.0.1:5001"})


def test_env_producto_no_puede_escapar_del_aislamiento(monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5001")
    monkeypatch.setenv("MLFLOW_REGISTRY_URI", "http://127.0.0.1:5001")
    # Las asignaciones explícitas de la fixture tienen prioridad sobre el shell.
    assert mlflow.get_tracking_uri().startswith("sqlite:///")
    assert mlflow.get_registry_uri().startswith("sqlite:///")


def test_servidor_integration_no_usa_puerto_producto(entorno_mlflow):
    assert entorno_mlflow.uri != "http://127.0.0.1:5001"
    assert entorno_mlflow.raiz.name.startswith("mlflow-aislado")
    assert mlflow.get_tracking_uri() == mlflow.get_registry_uri() == entorno_mlflow.uri
