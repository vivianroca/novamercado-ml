"""Política champion auditable. No entrena, no sirve modelos y no usa Airflow."""

import argparse
from contextlib import contextmanager
import csv
from datetime import date
import fcntl
import hashlib
import io
import json
import math
from pathlib import Path
import tempfile

from ml.tracking import EXPERIMENTO

ALIAS = "champion"
POLITICA = (
    "Costo total al menos 1% menor y estrictamente menor; MAE/RMSE/WAPE no "
    "empeoran más de 5%; costo por familia no empeora más de 10%. "
    "Mismas fechas, insumos y casos; métricas finitas, modelo READY, run FINISHED "
    "y ajuste/calibración anteriores a validación. Sin champion se compara con baseline."
)


@contextmanager
def _bloqueo(nombre):
    # Serializa escritores de esta herramienta en un mismo host.
    archivo = Path(tempfile.gettempdir()) / ("novamercado-champion-" + hashlib.sha256(nombre.encode()).hexdigest()[:16] + ".lock")
    with archivo.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _validar_metricas(reporte):
    m = reporte["metricas"]
    for clave in ("registros", "mae", "rmse", "wape", "costo_total", "costo_medio"):
        valor = m[clave]
        if clave == "wape" and valor is None:
            continue
        if type(valor) not in (float, int) or not math.isfinite(valor) or valor < 0:
            raise ValueError(f"Métrica inválida: {clave}")
    if type(m["registros"]) is not int or m["registros"] < 1:
        raise ValueError("No hay casos válidos")
    familias = reporte["por_familia"]
    if not familias:
        raise ValueError("Faltan métricas por familia")
    for f, valores in familias.items():
        costo = valores["costo_total"]
        if type(costo) not in (int, float) or not math.isfinite(costo) or costo < 0:
            raise ValueError(f"Costo inválido: {f}")
    if sum(v["registros"] for v in familias.values()) != m["registros"]:
        raise ValueError("Conteos por familia inconsistentes")
    if not math.isclose(sum(v["costo_total"] for v in familias.values()), m["costo_total"], rel_tol=1e-9, abs_tol=1e-6):
        raise ValueError("Costos por familia inconsistentes")


def decidir(candidato, referencia):
    """Decisión pura sobre reportes comparables; los empates conservan vigente."""
    _validar_metricas(candidato)
    _validar_metricas(referencia)
    if any(candidato[k] != referencia[k] for k in ("inicio", "fin")):
        raise ValueError("Periodos distintos: reevaluar el champion en el mismo periodo")
    if candidato["metricas"]["registros"] != referencia["metricas"]["registros"]:
        raise ValueError("No se evaluaron los mismos casos")
    if set(candidato["por_familia"]) != set(referencia["por_familia"]):
        raise ValueError("Familias distintas")
    if any(candidato["por_familia"][f]["registros"] != referencia["por_familia"][f]["registros"] for f in candidato["por_familia"]):
        raise ValueError("Casos por familia distintos")
    c, r = candidato["metricas"], referencia["metricas"]
    if c["costo_total"] >= r["costo_total"] or c["costo_total"] > r["costo_total"] * 0.99:
        return False, "Costo sin mejora mínima del 1% (incluye empate o retroceso)"
    for clave in ("mae", "rmse", "wape"):
        if c[clave] is None or r[clave] is None:
            if c[clave] != r[clave]:
                return False, f"{clave} no comparable"
        elif c[clave] > r[clave] * 1.05:
            return False, f"{clave} empeora más del 5%"
    for f, valores in candidato["por_familia"].items():
        if valores["costo_total"] > referencia["por_familia"][f]["costo_total"] * 1.10:
            return False, f"Costo de {f} empeora más del 10%"
    return True, f"Costo {c['costo_total']:.2f} vs {r['costo_total']:.2f}; cumple mejora y controles"


def _reporte(cliente, nombre, version):
    modelo = cliente.get_model_version(nombre, str(version))
    if modelo.status != "READY":
        raise ValueError("Modelo no está READY")
    run = cliente.get_run(modelo.run_id)
    if run.info.status != "FINISHED" or run.info.lifecycle_stage != "active":
        raise ValueError("Run de modelo no está FINISHED/activo")
    if cliente.get_experiment(run.info.experiment_id).name != EXPERIMENTO:
        raise ValueError("Modelo ajeno al experimento NovaMercado")
    with tempfile.TemporaryDirectory() as t:
        reporte = json.loads(Path(cliente.download_artifacts(modelo.run_id, "evaluacion/comparacion.json", t)).read_text())
    ajuste, cal_inicio, cal_fin, inicio, fin = [date.fromisoformat(reporte[k]) for k in
        ("ajuste_hasta", "calibracion_inicio", "calibracion_fin", "inicio", "fin")]
    if not ajuste < cal_inicio <= cal_fin < inicio <= fin:
        raise ValueError("Fuga temporal: cortes de ajuste/calibración inválidos")
    if not reporte.get("sha256_insumos"):
        raise ValueError("Falta linaje de insumos")
    _validar_metricas(reporte)
    if any(run.data.metrics.get(k) != v for k, v in reporte["metricas"].items() if v is not None):
        raise ValueError("Métricas del run y artefacto inconsistentes")
    return reporte


def _alias(cliente, nombre):
    valor = cliente.get_registered_model(nombre).aliases.get(ALIAS)
    return str(valor) if valor is not None else None


def _csv(filas):
    buffer = io.StringIO()
    campos = ["rol", "version", "inicio", "fin", "registros", "mae", "rmse", "wape", "costo_total", "costo_medio"]
    writer = csv.DictWriter(buffer, fieldnames=campos, lineterminator="\n")
    writer.writeheader()
    for rol, version, reporte in filas:
        writer.writerow({"rol": rol, "version": version or "", "inicio": reporte.get("inicio", ""),
            "fin": reporte.get("fin", ""), **{k: reporte.get("metricas", {}).get(k, "") for k in campos[4:]}})
    return buffer.getvalue()


def _markdown(nombre, candidato, anterior, decision):
    return (f"# Decisión champion\n\nModelo: `{nombre}`\n\n"
            f"Versión candidata: {candidato}\n\nChampion anterior: {anterior or 'ninguno'}\n\n"
            f"Champion al terminar: {decision['version'] or 'ninguno'}\n\n"
            f"Estado: {decision['estado']}\n\nPromovido: {decision['promovido']}\n\n"
            f"Criterio: {POLITICA}\n\nMotivo: {decision['motivo']}\n")


def evaluar_champion(cliente, nombre, version):
    """Un run de auditoría por evaluación; nunca sobrescribe decisiones anteriores."""
    experimento = cliente.get_experiment_by_name(EXPERIMENTO)
    if experimento is None:
        raise ValueError("No existe el experimento NovaMercado")
    with _bloqueo(nombre):
        auditoria = cliente.create_run(experimento.experiment_id, tags={
            "mlflow.runName": "decision-champion", "novamercado.tipo": "evaluacion_champion",
            "novamercado.modelo": nombre, "novamercado.version_candidato": str(version)})
        run_id = auditoria.info.run_id
        anterior = None
        intento_alias = False
        filas = [("candidato", str(version), {})]
        decision = {"estado": "fallido", "promovido": False, "version": None,
                    "motivo": "Evaluación no completada", "evaluacion_run_id": run_id}
        try:
            anterior = _alias(cliente, nombre)
            decision["version"] = anterior
            candidato = _reporte(cliente, nombre, version)
            filas = [("baseline", None, candidato["baseline"]), ("candidato", str(version), candidato)]
            if anterior:
                referencia = _reporte(cliente, nombre, anterior)
                filas.append(("champion", anterior, referencia))
                if candidato["sha256_insumos"] != referencia["sha256_insumos"]:
                    raise ValueError("Insumos distintos: reevaluar champion con los mismos datos")
            else:
                referencia = candidato["baseline"]
            promover, motivo = decidir(candidato, referencia)
            if anterior == str(version):
                promover, motivo = False, "La versión candidata ya es champion; se conserva"
            decision.update(estado="exitoso", promovido=False, motivo=motivo)
            # Ambos artefactos deben existir ANTES de intentar cambiar el alias.
            cliente.log_text(run_id, _csv(filas), "comparacion_modelos.csv")
            plan = {**decision, "estado": "pendiente_aplicacion" if promover else "exitoso",
                    "motivo": motivo + ("; promoción pendiente de confirmar" if promover else "")}
            cliente.log_text(run_id, _markdown(nombre, version, anterior, plan), "decision_champion.md")
            if _alias(cliente, nombre) != anterior:
                raise ValueError("Champion cambió durante evaluación; no sobrescribir")
            if promover:
                intento_alias = True
                cliente.set_registered_model_alias(nombre, ALIAS, str(version))
                if _alias(cliente, nombre) != str(version):
                    raise RuntimeError("No se confirmó la actualización de champion")
                decision.update(promovido=True, version=str(version))
            cliente.log_text(run_id, _markdown(nombre, version, anterior, decision), "decision_champion.md")
            cliente.set_terminated(run_id, status="FINISHED")
            return decision
        except Exception as error:
            # Compensar también un timeout que pudo ocurrir DESPUÉS del cambio.
            # No tocar un alias si otro escritor ya lo cambió a una tercera versión.
            error_reversion = None
            if intento_alias:
                try:
                    if _alias(cliente, nombre) == str(version):
                        if anterior is None:
                            cliente.delete_registered_model_alias(nombre, ALIAS)
                        else:
                            cliente.set_registered_model_alias(nombre, ALIAS, anterior)
                except Exception as rollback:
                    error_reversion = rollback
            decision.update(estado="fallido", promovido=False, motivo=f"{type(error).__name__}: {error}")
            if error_reversion:
                decision["motivo"] += f"; reversión no confirmada: {type(error_reversion).__name__}"
            try:
                try:
                    decision["version"] = _alias(cliente, nombre)
                except Exception:
                    decision["version"] = None  # Estado remoto no confirmable.
                cliente.log_text(run_id, _csv(filas), "comparacion_modelos.csv")
                cliente.log_text(run_id, _markdown(nombre, version, anterior, decision), "decision_champion.md")
            finally:
                cliente.set_terminated(run_id, status="FAILED")
            if error_reversion:
                # No ocultar incertidumbre remota ni declarar conservación sin comprobar.
                raise RuntimeError(decision["motivo"]) from error
            return decision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modelo", default="novamercado-histgradientboosting")
    parser.add_argument("--version", required=True)
    parser.add_argument("--tracking-uri", default="http://127.0.0.1:5001")
    args = parser.parse_args()
    from mlflow import MlflowClient, set_tracking_uri
    set_tracking_uri(args.tracking_uri)
    decision = evaluar_champion(MlflowClient(tracking_uri=args.tracking_uri), args.modelo, args.version)
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    if decision["estado"] == "fallido":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
