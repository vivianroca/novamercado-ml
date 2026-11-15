"""Carga explícita de insumos; sin IO al importar."""

import csv
from datetime import date
from pathlib import Path

from ml.baseline import Costos, Venta


def cargar_datos(directorio):
    directorio = Path(directorio)

    def leer(nombre):
        with (directorio / nombre).open(encoding="utf-8-sig", newline="") as archivo:
            return list(csv.DictReader(archivo))

    costos = {}
    for fila in leer("costos.csv"):
        familia = fila["familia_id"]
        if familia in costos:
            raise ValueError("Familia duplicada en costos.csv")
        costos[familia] = Costos(float(fila["costo_faltante"]), float(fila["costo_sobrante"]))
    tiendas = {int(f["tienda_id"]): date.fromisoformat(f["fecha_apertura"]) for f in leer("tiendas.csv")}
    familias = {f["familia_id"] for f in leer("familias.csv")}
    if set(costos) != familias:
        raise ValueError("Costos y catálogo de familias no coinciden")
    historial, claves = [], set()
    for fila in leer("historico_ventas.csv"):
        venta = Venta(date.fromisoformat(fila["fecha"]), int(fila["tienda_id"]), fila["familia_id"], int(fila["ventas"]))
        clave = (venta.fecha, venta.tienda_id, venta.familia_id)
        if clave in claves:
            raise ValueError("Duplicados en histórico; reconciliar antes de evaluar")
        if venta.tienda_id not in tiendas or venta.familia_id not in familias:
            raise ValueError("Referencia desconocida en histórico")
        if venta.fecha < tiendas[venta.tienda_id]:
            raise ValueError("Ventas anteriores a apertura de tienda")
        claves.add(clave)
        historial.append(venta)
    if not historial:
        raise ValueError("Histórico vacío")
    return historial, costos
