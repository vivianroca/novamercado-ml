"""Ajuste único, calibración temporal previa y comparación fuera de muestra."""

from collections import defaultdict
from datetime import timedelta
from math import ceil
import time

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from ml.baseline import costo_negocio
from ml.evaluacion import evaluar_temporal, metricas
from ml.features import CATEGORICAS, NOMBRES

PARAMETROS = dict(loss="squared_error", learning_rate=0.08, max_iter=200,
                  max_leaf_nodes=31, min_samples_leaf=30, l2_regularization=1.0,
                  early_stopping=False, categorical_features=CATEGORICAS, random_state=42)


def ajuste_cuantil(residuos, costos):
    if not residuos or not np.isfinite(residuos).all():
        raise ValueError("Residuos de calibración vacíos o inválidos")
    indice = max(0, min(len(residuos) - 1, ceil(len(residuos) * costos.cuantil) - 1))
    return float(sorted(residuos)[indice])


def evaluar_histgradient(x, ventas, costos, inicio, fin, dias_calibracion=28, parametros=None):
    if inicio > fin or dias_calibracion < 1:
        raise ValueError("Cortes temporales inválidos")
    x = np.asarray(x, dtype=float)
    if x.shape != (len(ventas), len(NOMBRES)):
        raise ValueError("Matriz y ventas desalineadas")
    inicio_cal = inicio - timedelta(days=dias_calibracion)
    ajuste = np.array([v.fecha < inicio_cal for v in ventas])
    calibracion = np.array([inicio_cal <= v.fecha < inicio for v in ventas])
    validacion = np.array([inicio <= v.fecha <= fin for v in ventas])
    if not all(m.any() for m in (ajuste, calibracion, validacion)):
        raise ValueError("Se requieren ajuste, calibración y validación no vacíos")
    y = np.array([v.ventas for v in ventas], dtype=float)
    configuracion = {**PARAMETROS, **(parametros or {})}
    if configuracion["early_stopping"] is not False:
        raise ValueError("No permitir partición aleatoria interna para early stopping")
    modelo = HistGradientBoostingRegressor(**configuracion)
    reloj = time.monotonic()
    with threadpool_limits(limits=2):
        modelo.fit(x[ajuste], y[ajuste])
        pred_cal = np.maximum(0, modelo.predict(x[calibracion]))
        pred_val = np.maximum(0, modelo.predict(x[validacion]))
    residuos = defaultdict(list)
    for v, pred in zip(np.array(ventas, dtype=object)[calibracion], pred_cal):
        residuos[v.familia_id].append(v.ventas - pred)
    familias = {v.familia_id for v in np.array(ventas, dtype=object)[validacion]}
    if familias - residuos.keys():
        raise ValueError("Familia sin residuos de calibración")
    ajustes = {f: ajuste_cuantil(valores, costos[f]) for f, valores in residuos.items()}
    resultados = []
    for v, pred in zip(np.array(ventas, dtype=object)[validacion], pred_val):
        sugerido = max(0, int(float(pred) + ajustes[v.familia_id] + 0.5))
        resultados.append({"fecha": v.fecha.isoformat(), "tienda_id": v.tienda_id,
            "familia_id": v.familia_id, "real": v.ventas, "venta_esperada": float(pred),
            "cantidad_sugerida": sugerido, "costo": costo_negocio(v.ventas, sugerido, costos[v.familia_id]),
            "costo_media": costo_negocio(v.ventas, int(float(pred) + 0.5), costos[v.familia_id])})
    baseline, filas_base = evaluar_temporal(ventas, costos, inicio, fin)
    claves = lambda filas: [(f["fecha"], f["tienda_id"], f["familia_id"]) for f in filas]
    if claves(resultados) != claves(filas_base):
        raise ValueError("Baseline y candidato deben evaluarse en exactamente los mismos casos")
    por_familia = defaultdict(list)
    for fila in resultados:
        por_familia[fila["familia_id"]].append(fila)
    reporte = {"modelo": "HistGradientBoostingRegressor", "inicio": inicio.isoformat(), "fin": fin.isoformat(),
        "ajuste_hasta": max(v.fecha for v in np.array(ventas, dtype=object)[ajuste]).isoformat(),
        "calibracion_inicio": inicio_cal.isoformat(), "calibracion_fin": (inicio - timedelta(days=1)).isoformat(),
        "filas_ajuste": int(ajuste.sum()), "filas_calibracion": int(calibracion.sum()),
        "filas_validacion": int(validacion.sum()), "parametros": configuracion, "features": NOMBRES,
        "ajustes_por_familia": ajustes, "metricas": metricas(resultados),
        "por_familia": {f: metricas(filas) for f, filas in sorted(por_familia.items())},
        "baseline": baseline, "segundos_ajuste_evaluacion": time.monotonic() - reloj,
        "protocolo": "pesos fijos; rezagos D usan solo observaciones anteriores a D"}
    return modelo, reporte, resultados
