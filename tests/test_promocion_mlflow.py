"""Auditoría HTTP con modelos sintéticos en tracking de pytest aislado."""

from pathlib import Path
import tempfile

import pytest

from ml.promocion import evaluar_champion


@pytest.fixture
def cliente(entorno_mlflow):
    return entorno_mlflow.cliente


@pytest.mark.parametrize("inexistente", [False, True])
def test_decision_real_conserva_alias_y_ambos_artefactos(cliente, entorno_mlflow, inexistente):
    nombre = entorno_mlflow.modelo_nombre
    anterior = cliente.get_registered_model(nombre).aliases.get("champion")
    assert anterior is not None
    version = "999999999" if inexistente else str(anterior)
    d = evaluar_champion(cliente, nombre, version)
    assert d["estado"] == ("fallido" if inexistente else "exitoso")
    assert d["promovido"] is False and d["version"] == str(anterior)
    assert cliente.get_registered_model(nombre).aliases["champion"] == str(anterior)
    assert cliente.get_run(d["evaluacion_run_id"]).info.status == ("FAILED" if inexistente else "FINISHED")
    with tempfile.TemporaryDirectory() as t:
        for archivo in ("comparacion_modelos.csv", "decision_champion.md"):
            ruta = Path(cliente.download_artifacts(d["evaluacion_run_id"], archivo, t))
            assert ruta.read_text()
        texto = (Path(t) / "decision_champion.md").read_text()
        assert f"Champion al terminar: {anterior}" in texto
        assert "Criterio:" in texto and "Motivo:" in texto
