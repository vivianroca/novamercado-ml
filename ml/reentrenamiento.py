"""Snapshot de producto → entrenamiento; promoción en un paso separado del DAG."""

import argparse
import csv
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from app.db.conexion import conectar_producto
from ml.datos import cargar_datos
from ml.tracking import INSUMOS, sha256


def leer_fuente_producto(conectar=conectar_producto, fecha_fin=None):
    with conectar() as conexion:
        conexion.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        observaciones = conexion.execute(
            """SELECT fecha, tienda_id, familia_id, ventas FROM novamercado.observaciones
               WHERE (%s::date IS NULL OR fecha <= %s::date)
               ORDER BY fecha, tienda_id, familia_id""", (fecha_fin, fecha_fin)).fetchall()
        solicitudes = conexion.execute(
            """SELECT canonica FROM novamercado.solicitudes
               WHERE tipo='prediccion' AND (%s::date IS NULL OR fecha <= %s::date)
               ORDER BY creada_en, id""", (fecha_fin, fecha_fin)).fetchall()
    return observaciones, [fila[0] for fila in solicitudes]


def construir_snapshot(data_dir, destino, observaciones, solicitudes, fecha_fin=None):
    data_dir, destino = Path(data_dir), Path(destino)
    # Validar histórico publicado antes de reconciliar; no esconder duplicados.
    cargar_datos(data_dir)
    destino.mkdir(parents=True, exist_ok=True)
    for nombre in ("tiendas.csv", "familias.csv", "costos.csv", "feriados.csv"):
        shutil.copy2(data_dir / nombre, destino / nombre)
    with (data_dir / "historico_ventas.csv").open(encoding="utf-8-sig", newline="") as archivo:
        filas = list(csv.DictReader(archivo))
    columnas = ["fecha", "tienda_id", "familia_id", "ventas", "en_promocion"]
    clave = lambda f: (f["fecha"], int(f["tienda_id"]), f["familia_id"])
    unificado = {clave(f): {c: f[c] for c in columnas} for f in filas
                 if fecha_fin is None or date.fromisoformat(f["fecha"]) <= fecha_fin}
    promos = {}
    for solicitud in solicitudes:
        for familia in solicitud["familias"]:
            k = (solicitud["fecha"], solicitud["tienda_id"], familia["familia_id"])
            promos[k] = familia["en_promocion"]  # Última solicitud canónica por familia.
    nuevas = corregidas = faltantes = 0
    observaciones_usadas = []
    vistos = set()
    for fecha, tienda, familia, ventas in observaciones:
        if fecha_fin is not None and fecha > fecha_fin:
            continue
        k = (fecha.isoformat(), tienda, familia)
        if k in vistos:
            raise ValueError("Observaciones duplicadas en el snapshot")
        vistos.add(k)
        anterior = unificado.get(k)
        if anterior is None:
            nuevas += 1
            promo = promos.get(k)
            if promo is None:
                faltantes += 1
            unificado[k] = {"fecha": fecha.isoformat(), "tienda_id": tienda, "familia_id": familia,
                            "ventas": ventas, "en_promocion": promo if promo is not None else ""}
        else:
            corregidas += int(int(anterior["ventas"]) != ventas)
            anterior["ventas"] = ventas
        observaciones_usadas.append([fecha.isoformat(), tienda, familia, ventas])
    if not unificado:
        raise ValueError("Snapshot vacío")
    with (destino / "historico_ventas.csv").open("w", newline="") as archivo:
        writer = csv.DictWriter(archivo, fieldnames=columnas, lineterminator="\n")
        writer.writeheader()
        writer.writerows(unificado[k] for k in sorted(unificado))
    cargar_datos(destino)  # Referencias, negativos, apertura e idempotencia de claves.
    digest = lambda valor: hashlib.sha256(json.dumps(valor, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {"sha256_originales": {n: sha256(data_dir / n) for n in (*INSUMOS, "feriados.csv")},
            "sha256_observaciones": digest(sorted(observaciones_usadas)),
            "sha256_promociones": digest(sorted([list(k) + [v] for k, v in promos.items()])),
            "observaciones_leidas": len(observaciones_usadas), "filas_nuevas": nuevas,
            "filas_corregidas": corregidas, "promociones_no_disponibles": faltantes,
            "registros": len(unificado), "fecha_fin_efectiva": max(k[0] for k in unificado)}


def entrenar_desde_producto(data_dir, salida, run_id, fecha_fin=None, conectar=conectar_producto):
    from ml.entrenamiento import entrenar_y_registrar
    observaciones, solicitudes = leer_fuente_producto(conectar, fecha_fin)
    with tempfile.TemporaryDirectory(prefix="novamercado-snapshot-") as temporal:
        manifest = construir_snapshot(data_dir, temporal, observaciones, solicitudes, fecha_fin)
        manifest["airflow_run_id"] = run_id
        fin = date.fromisoformat(manifest["fecha_fin_efectiva"])
        reporte = entrenar_y_registrar(temporal, fin - timedelta(days=55), fin,
            os.environ["MLFLOW_TRACKING_URI"], salida, promover=False,
            nombre_modelo=os.environ.get("MODEL_NAME", "novamercado-histgradientboosting"),
            linaje_extra=manifest)
    return {"nombre": os.environ.get("MODEL_NAME", "novamercado-histgradientboosting"),
            "version": reporte["mlflow"]["version"], "run_id": reporte["mlflow"]["run_id"],
            "manifesto": str(Path(salida).resolve())}


def promover_desde_manifesto(manifesto):
    import mlflow
    from ml.promocion import ReferenciaEvaluada, evaluar_champion
    reporte = json.loads(Path(manifesto).read_text())
    uri = os.environ["MLFLOW_TRACKING_URI"]
    mlflow.set_tracking_uri(uri)
    mlflow.set_registry_uri(uri)
    referencia = reporte.get("referencia_champion")
    return evaluar_champion(mlflow.MlflowClient(tracking_uri=uri, registry_uri=uri),
        os.environ.get("MODEL_NAME", "novamercado-histgradientboosting"),
        reporte["mlflow"]["version"], ReferenciaEvaluada(**referencia) if referencia else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("modo", choices=["entrenar", "promover"])
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "data"))
    parser.add_argument("--salida", required=True)
    parser.add_argument("--manifesto")
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--fecha-fin", type=date.fromisoformat)
    args = parser.parse_args()
    if args.modo == "entrenar":
        resultado = entrenar_desde_producto(args.data_dir, args.salida, args.run_id, args.fecha_fin)
        # El reporte ya está en salida; el resumen solo viaja por stdout.
    else:
        if not args.manifesto:
            parser.error("promover requiere --manifesto")
        resultado = promover_desde_manifesto(args.manifesto)
        Path(args.salida).write_text(json.dumps(resultado, ensure_ascii=False) + "\n")
    print(json.dumps(resultado, ensure_ascii=False))
    if resultado.get("estado") == "fallido":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
