import json
from types import SimpleNamespace

import pytest

from ml.tracking import EXPERIMENTO, INSUMOS, registrar_baseline, sha256


class ClientePrueba:
    def __init__(self):
        self.experimento = None
        self.creados = []
        self.parametros = {}
        self.metricas = {}
        self.artefactos = {}
        self.archivos = []
        self.estados = []
        self.inputs = []

    def get_experiment_by_name(self, nombre):
        assert nombre == EXPERIMENTO
        return self.experimento

    def create_experiment(self, nombre):
        self.creados.append(nombre)
        self.experimento = SimpleNamespace(experiment_id="1")
        return "1"

    def create_run(self, experimento, tags):
        assert experimento == "1"
        assert tags["novamercado.operacion"] == "registro_sin_entrenamiento"
        return SimpleNamespace(info=SimpleNamespace(run_id="run-prueba"))

    def log_param(self, run, nombre, valor): self.parametros[nombre] = valor
    def log_metric(self, run, nombre, valor): self.metricas[nombre] = valor
    def log_dict(self, run, valor, ruta): self.artefactos[ruta] = valor
    def log_artifact(self, run, ruta, destino): self.archivos.append((ruta, destino))
    def log_inputs(self, run, inputs): self.inputs = inputs
    def set_terminated(self, run, status): self.estados.append(status)


@pytest.fixture
def reporte(tmp_path):
    for nombre in INSUMOS:
        (tmp_path / nombre).write_text("contenido-sintetico")
    datos = {"baseline": "media_semanal_cuantil_empirico", "ventana_dias": 56,
             "inicio": "2026-01-04", "fin": "2026-02-28", "entrenamiento_hasta": "2026-01-03",
             "protocolo": "diario", "metricas": {"mae": 2.5, "wape": None},
             "por_familia": {"pan": {"costo_total": 10}},
             "sha256_insumos": {n: sha256(tmp_path / n) for n in INSUMOS}}
    ruta = tmp_path / "reporte.json"
    ruta.write_text(json.dumps(datos))
    return ruta, tmp_path


def test_registra_y_reutiliza_unico_experimento_sin_servidor(reporte):
    ruta, directorio = reporte
    cliente = ClientePrueba()
    for _ in range(2):
        assert registrar_baseline(ruta, directorio, cliente=cliente) == "run-prueba"
    assert cliente.creados == ["NovaMercado"]
    assert cliente.estados == ["FINISHED", "FINISHED"]
    assert cliente.parametros["ventana_dias"] == 56
    assert cliente.metricas == {"mae": 2.5, "familia/pan/costo_total": 10}
    assert set(cliente.artefactos) == {"evaluacion/reporte.json", "linaje/manifest.json", "baseline/configuracion.json"}
    assert len(cliente.inputs) == 4
    assert {i.dataset.name for i in cliente.inputs} == set(INSUMOS)
    assert all(len(i.dataset.digest) == 32 for i in cliente.inputs)
    assert all(not ruta.endswith(".csv") for ruta, _ in cliente.archivos)
    assert all(not destino.endswith("/.") for _, destino in cliente.archivos)
    assert cliente.artefactos["linaje/manifest.json"]["sha256_reporte"] == sha256(ruta)


def test_insumo_modificado_rechaza_antes_de_crear_run(reporte):
    ruta, directorio = reporte
    (directorio / "costos.csv").write_text("cambiado")
    cliente = ClientePrueba()
    with pytest.raises(ValueError, match="hashes"):
        registrar_baseline(ruta, directorio, cliente=cliente)
    assert cliente.creados == []


@pytest.mark.parametrize("alterar", ["fecha", "metrica", "baseline"])
def test_reporte_invalido_no_se_registra(reporte, alterar):
    ruta, directorio = reporte
    datos = json.loads(ruta.read_text())
    if alterar == "fecha": datos["entrenamiento_hasta"] = datos["inicio"]
    if alterar == "metrica": datos["metricas"]["mae"] = float("nan")
    if alterar == "baseline": datos["baseline"] = "otro_modelo"
    ruta.write_text(json.dumps(datos))
    with pytest.raises(ValueError):
        registrar_baseline(ruta, directorio, cliente=ClientePrueba())


def test_fallo_subida_marca_failed(reporte):
    ruta, directorio = reporte
    cliente = ClientePrueba()
    def fallo(*args): raise RuntimeError("subida fallida")
    cliente.log_dict = fallo
    with pytest.raises(RuntimeError, match="subida fallida"):
        registrar_baseline(ruta, directorio, cliente=cliente)
    assert cliente.estados == ["FAILED"]


def test_linaje_sin_git_en_imagen_no_inventa_commit(monkeypatch):
    from ml.tracking import proveniencia_git
    def ausente(*args, **kwargs): raise FileNotFoundError("git no instalado")
    monkeypatch.setattr("ml.tracking.subprocess.check_output", ausente)
    monkeypatch.delenv("NOVAMERCADO_GIT_COMMIT", raising=False)
    assert proveniencia_git() == (None, None)
