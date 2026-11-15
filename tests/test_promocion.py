import copy
import csv
import io
import json
from pathlib import Path
from types import SimpleNamespace as Obj

import pytest

from ml.promocion import decidir, evaluar_champion, ReferenciaEvaluada


def reporte(costo=90, mae=10):
    m = {"registros": 10, "mae": mae, "rmse": 15.0, "wape": 0.2,
         "costo_total": costo, "costo_medio": costo / 10}
    base = {"inicio": "2026-01-04", "fin": "2026-02-28",
            "metricas": {**m, "costo_total": 100, "costo_medio": 10},
            "por_familia": {"pan": {"registros": 10, "costo_total": 100}}}
    return {"inicio": base["inicio"], "fin": base["fin"], "metricas": m,
            "por_familia": {"pan": {"registros": 10, "costo_total": costo}},
            "ajuste_hasta": "2025-11-30", "calibracion_inicio": "2025-12-01",
            "calibracion_fin": "2026-01-03", "baseline": base,
            "sha256_insumos": {"historico_ventas.csv": "hash_sintetico"}}


class RegistryPrueba:
    def __init__(self, anterior="2"):
        self.alias = anterior
        self.reportes = {"1": reporte(90), "2": reporte(100)}
        self.artefactos = {}
        self.cambios = []
        self.estado = None
        self.fallo_csv = False
        self.fallo_alias = False
        self.fallo_alias_despues = False
        self.fallo_final = False
        self.md_count = 0
        self.referencias = {}

    def get_experiment_by_name(self, nombre): return Obj(experiment_id="1")
    def get_experiment(self, identificador): return Obj(name="NovaMercado")
    def create_run(self, experimento, tags): return Obj(info=Obj(run_id="auditoria"))
    def get_registered_model(self, nombre): return Obj(aliases={"champion": self.alias} if self.alias else {})
    def get_model_version(self, nombre, version): return Obj(status="READY", run_id=version)
    def get_run(self, run_id):
        return Obj(info=Obj(status="FINISHED", lifecycle_stage="active", experiment_id="1"),
                   data=Obj(metrics=self.reportes[run_id]["metricas"]))

    def download_artifacts(self, run_id, ruta, destino):
        archivo = Path(destino) / "reporte.json"
        archivo.write_text(json.dumps(self.reportes[run_id]))
        return str(archivo)

    def log_text(self, run_id, texto, nombre):
        if nombre.endswith(".csv") and self.fallo_csv:
            self.fallo_csv = False
            raise OSError("No se pudo subir CSV")
        if nombre.endswith(".md"):
            self.md_count += 1
            if self.md_count == 2 and self.fallo_final:
                raise OSError("Falló confirmación de artefacto")
        self.artefactos[nombre] = texto

    def log_dict(self, run_id, objeto, nombre):
        self.referencias[nombre] = objeto

    def set_registered_model_alias(self, nombre, alias, version):
        assert set(self.artefactos) == {"comparacion_modelos.csv", "decision_champion.md"}
        if self.fallo_alias:
            raise OSError("No se puede cambiar alias")
        self.cambios.append(version)
        self.alias = version
        if self.fallo_alias_despues:
            self.fallo_alias_despues = False
            raise TimeoutError("Respuesta perdida después de cambiar alias")

    def delete_registered_model_alias(self, nombre, alias): self.alias = None
    def set_terminated(self, run_id, status): self.estado = status


def test_mejora_promueve_y_artefactos_explican_version():
    cliente = RegistryPrueba()
    d = evaluar_champion(cliente, "modelo", "1")
    assert d["promovido"] is True and d["version"] == "1"
    assert cliente.alias == "1" and cliente.estado == "FINISHED"
    csv_filas = list(csv.DictReader(io.StringIO(cliente.artefactos["comparacion_modelos.csv"])))
    assert [f["rol"] for f in csv_filas] == ["baseline", "candidato", "champion"]
    assert [f["costo_total"] for f in csv_filas] == ["100", "90", "100"]
    assert "Champion al terminar: 1" in cliente.artefactos["decision_champion.md"]
    assert "1%" in cliente.artefactos["decision_champion.md"]


@pytest.mark.parametrize("costo", [100, 101, 99.5])
def test_empate_retroceso_y_mejora_insuficiente_conservan(costo):
    cliente = RegistryPrueba()
    cliente.reportes["1"] = reporte(costo)
    d = evaluar_champion(cliente, "modelo", "1")
    assert not d["promovido"] and d["version"] == "2"
    assert cliente.alias == "2" and cliente.cambios == []
    assert len(cliente.artefactos) == 2


def test_primer_champion_contra_baseline():
    cliente = RegistryPrueba(anterior=None)
    assert evaluar_champion(cliente, "modelo", "1")["promovido"]
    assert cliente.alias == "1"


def test_primer_candidato_sin_mejora_no_crea_alias():
    cliente = RegistryPrueba(anterior=None)
    cliente.reportes["1"] = reporte(110)
    assert not evaluar_champion(cliente, "modelo", "1")["promovido"]
    assert cliente.alias is None


def test_ya_champion_no_se_repromueve():
    cliente = RegistryPrueba(anterior="1")
    d = evaluar_champion(cliente, "modelo", "1")
    assert not d["promovido"] and d["version"] == "1" and cliente.cambios == []


@pytest.mark.parametrize("clave", ["mae", "rmse", "wape"])
def test_control_tecnico_rechaza(clave):
    c, r = reporte(90), reporte(100)
    c["metricas"][clave] = r["metricas"][clave] * 1.06
    assert decidir(c, r)[0] is False


def test_control_por_familia_rechaza_aunque_baje_total():
    c, r = reporte(90), reporte(100)
    c["por_familia"] = {"pan": {"registros": 5, "costo_total": 60}, "otra": {"registros": 5, "costo_total": 30}}
    r["por_familia"] = {"pan": {"registros": 5, "costo_total": 50}, "otra": {"registros": 5, "costo_total": 50}}
    assert decidir(c, r) == (False, "Costo de pan empeora más del 10%")


@pytest.mark.parametrize("defecto", ["periodo", "insumos", "nan", "fuga", "conteos"])
def test_no_comparable_o_invalido_no_toca_alias(defecto):
    cliente = RegistryPrueba()
    r = cliente.reportes["1"]
    if defecto == "periodo": r["fin"] = "2026-03-01"
    if defecto == "insumos": r["sha256_insumos"] = {"historico_ventas.csv": "distinto"}
    if defecto == "nan": r["metricas"]["mae"] = float("nan")
    if defecto == "fuga": r["calibracion_fin"] = r["inicio"]
    if defecto == "conteos": r["metricas"]["registros"] = 11
    d = evaluar_champion(cliente, "modelo", "1")
    assert d["estado"] == "fallido" and d["promovido"] is False
    assert cliente.alias == "2" and cliente.cambios == [] and cliente.estado == "FAILED"
    assert set(cliente.artefactos) == {"comparacion_modelos.csv", "decision_champion.md"}


@pytest.mark.parametrize("fallo", ["fallo_csv", "fallo_alias", "fallo_alias_despues", "fallo_final"])
def test_errores_conservan_o_revierten_champion(fallo):
    cliente = RegistryPrueba()
    setattr(cliente, fallo, True)
    d = evaluar_champion(cliente, "modelo", "1")
    assert d["estado"] == "fallido" and not d["promovido"]
    assert d["version"] == cliente.alias == "2"
    assert "fallido" in cliente.artefactos["decision_champion.md"]


def test_error_final_sin_champion_revierte_alias_creado():
    cliente = RegistryPrueba(anterior=None)
    cliente.fallo_final = True
    d = evaluar_champion(cliente, "modelo", "1")
    assert not d["promovido"] and cliente.alias is None


def test_comparacion_no_muta_reportes():
    c, r = reporte(90), reporte(100)
    antes = copy.deepcopy((c, r))
    assert decidir(c, r)[0]
    assert (c, r) == antes


def test_cambio_externo_de_alias_no_se_sobrescribe():
    cliente = RegistryPrueba()
    original = cliente.get_registered_model
    llamadas = 0
    def consultar(nombre):
        nonlocal llamadas
        llamadas += 1
        if llamadas == 2:
            cliente.alias = "3"
        return original(nombre)
    cliente.get_registered_model = consultar
    d = evaluar_champion(cliente, "modelo", "1")
    assert d["estado"] == "fallido" and d["version"] == "3"
    assert cliente.alias == "3" and cliente.cambios == []


def test_costo_cero_y_limite_exacto():
    assert decidir(reporte(99), reporte(100))[0] is True
    assert decidir(reporte(0), reporte(0))[0] is False


@pytest.mark.parametrize("estado", ["FAILED", "RUNNING"])
def test_run_incompleto_no_puede_promover(estado):
    cliente = RegistryPrueba()
    original = cliente.get_run
    def run(run_id):
        resultado = original(run_id)
        resultado.info.status = estado
        return resultado
    cliente.get_run = run
    decision = evaluar_champion(cliente, "modelo", "1")
    assert decision["estado"] == "fallido"
    assert cliente.alias == "2" and not cliente.cambios


def test_reevaluacion_en_nuevo_periodo_sin_modificar_run_champion():
    cliente = RegistryPrueba()
    origen = copy.deepcopy(cliente.reportes["2"])
    c = cliente.reportes["1"]
    c.update(inicio="2026-03-01", fin="2026-04-30", sha256_insumos={"historico_ventas.csv": "snapshot_nuevo"})
    actualizada = {**copy.deepcopy(origen), "inicio": c["inicio"], "fin": c["fin"],
                   "sha256_insumos": c["sha256_insumos"], "reevaluado_sin_entrenar": True}
    d = evaluar_champion(cliente, "modelo", "1", ReferenciaEvaluada("2", actualizada))
    assert d["promovido"] and cliente.alias == "1"
    assert cliente.reportes["2"] == origen
    assert cliente.referencias["evaluacion/champion_reevaluado.json"] == actualizada


@pytest.mark.parametrize("defecto", ["version", "cortes", "error"])
def test_reevaluacion_invalida_conserva_champion(defecto):
    cliente = RegistryPrueba()
    r = copy.deepcopy(cliente.reportes["2"])
    version = "9" if defecto == "version" else "2"
    if defecto == "cortes": r["calibracion_fin"] = "2026-01-02"
    referencia = ReferenciaEvaluada(version, r, "Falló evaluación" if defecto == "error" else None)
    d = evaluar_champion(cliente, "modelo", "1", referencia)
    assert d["estado"] == "fallido" and cliente.alias == "2" and not cliente.cambios
