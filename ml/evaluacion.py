"""Evaluación diaria progresiva: observar D solo después de predecir todo D."""

import argparse
from collections import defaultdict
from datetime import date
import json
from math import sqrt

from ml.baseline import BaselineSemanal, costo_negocio
from ml.datos import cargar_datos


def metricas(filas):
    if not filas:
        raise ValueError("No hay predicciones para evaluar")
    n = len(filas)
    errores = [abs(f["real"] - f["venta_esperada"]) for f in filas]
    total_real = sum(f["real"] for f in filas)
    return {"registros": n, "mae": sum(errores) / n,
            "rmse": sqrt(sum(e * e for e in errores) / n),
            "wape": sum(errores) / total_real if total_real else None,
            "costo_total": sum(f["costo"] for f in filas),
            "costo_medio": sum(f["costo"] for f in filas) / n,
            "costo_sugerido_media": sum(f["costo_media"] for f in filas)}


def evaluar_temporal(historial, costos, inicio: date, fin: date, ventana_dias=56):
    if inicio > fin:
        raise ValueError("Intervalo temporal inválido")
    historial = list(historial)
    claves = [(v.fecha, v.tienda_id, v.familia_id) for v in historial]
    if len(set(claves)) != len(claves):
        raise ValueError("Histórico duplicado")
    entrenamiento = [v for v in historial if v.fecha < inicio]
    if not entrenamiento:
        raise ValueError("Se requiere entrenamiento estrictamente anterior a validación")
    modelo = BaselineSemanal(entrenamiento, costos, ventana_dias)
    dias = defaultdict(list)
    for venta in historial:
        if inicio <= venta.fecha <= fin:
            dias[venta.fecha].append(venta)
    resultados = []
    for dia, observaciones in sorted(dias.items()):
        for venta in sorted(observaciones, key=lambda v: (v.tienda_id, v.familia_id)):
            p = modelo.predecir(venta.tienda_id, venta.familia_id, dia)
            costos_familia = costos[venta.familia_id]
            resultados.append({"fecha": dia.isoformat(), "tienda_id": venta.tienda_id,
                "familia_id": venta.familia_id, "real": venta.ventas,
                "venta_esperada": p.venta_esperada, "cantidad_sugerida": p.cantidad_sugerida,
                "costo": costo_negocio(venta.ventas, p.cantidad_sugerida, costos_familia),
                "costo_media": costo_negocio(venta.ventas, int(p.venta_esperada + 0.5), costos_familia)})
        modelo.agregar(observaciones)
    por_familia = defaultdict(list)
    for fila in resultados:
        por_familia[fila["familia_id"]].append(fila)
    reporte = {"baseline": "media_semanal_cuantil_empirico", "ventana_dias": ventana_dias,
        "inicio": inicio.isoformat(), "fin": fin.isoformat(),
        "entrenamiento_hasta": max(v.fecha for v in entrenamiento).isoformat(),
        "protocolo": "diario: predecir D, incorporar observaciones D después",
        "metricas": metricas(resultados),
        "por_familia": {f: metricas(filas) for f, filas in sorted(por_familia.items())}}
    return reporte, resultados


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--inicio", required=True, type=date.fromisoformat)
    parser.add_argument("--fin", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    historial, costos = cargar_datos(args.data_dir)
    reporte, _ = evaluar_temporal(historial, costos, args.inicio, args.fin)
    print(json.dumps(reporte, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
