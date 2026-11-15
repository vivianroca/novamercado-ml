"""Variables causales por tienda/familia; promoción y calendario conocidos de D."""

import calendar
import csv
from dataclasses import dataclass
from datetime import date, timedelta
from math import cos, sin, pi
from pathlib import Path

import numpy as np

from ml.baseline import Venta

TIPOS_EVENTO = ("feriado", "comercial", "pago", "medio_dia")
NOMBRES = ["tienda", "familia", "ciudad", "formato", "edad_tienda", "anio", "mes", "dia",
           "dia_semana", "dia_anio_sin", "dia_anio_cos", "fin_mes", "quincena", "en_promocion"]
NOMBRES += [f"{ambito}_{tipo}" for ambito in ("nacional", "local") for tipo in TIPOS_EVENTO]
NOMBRES += ["lag_1", "lag_7", "lag_14", "lag_28"]
NOMBRES += [f"{estadistico}_{dias}" for dias in (7, 28, 56) for estadistico in ("media", "std", "conteo")]
NOMBRES += ["media_mismo_dia_semana_56"]
CATEGORICAS = [0, 1, 2, 3]


@dataclass
class Contexto:
    tiendas: dict
    familias: dict
    ciudades: dict
    formatos: dict
    eventos: dict

    @classmethod
    def cargar(cls, directorio):
        def leer(nombre):
            with (Path(directorio) / nombre).open(encoding="utf-8-sig", newline="") as archivo:
                return list(csv.DictReader(archivo))
        tiendas = {int(f["tienda_id"]): f for f in leer("tiendas.csv")}
        familias = {f["familia_id"]: i for i, f in enumerate(sorted(leer("familias.csv"), key=lambda f: f["familia_id"]))}
        ciudades = {c: i for i, c in enumerate(sorted({t["ciudad"] for t in tiendas.values()}))}
        formatos = {c: i for i, c in enumerate(sorted({t["tipo"] for t in tiendas.values()}))}
        eventos = {}
        for f in leer("feriados.csv"):
            if f["ambito"] != "nacional" and f["ambito"] not in ciudades:
                raise ValueError("Ámbito de feriado desconocido")
            if f["tipo"] not in TIPOS_EVENTO:
                raise ValueError("Tipo de evento desconocido")
            eventos.setdefault((date.fromisoformat(f["fecha"]), f["ambito"]), set()).add(f["tipo"])
        return cls(tiendas, familias, ciudades, formatos, eventos)


class FeaturesCausales:
    def __init__(self, contexto):
        self.contexto = contexto
        self.historial = {}

    def agregar(self, ventas):
        ventas = list(ventas)
        claves = [(v.tienda_id, v.familia_id, v.fecha) for v in ventas]
        if len(set(claves)) != len(claves) or any(f in self.historial.get((t, fam), {}) for t, fam, f in claves):
            raise ValueError("Observación duplicada en features")
        for v in ventas:
            self.historial.setdefault((v.tienda_id, v.familia_id), {})[v.fecha] = v.ventas

    def fila(self, tienda_id, familia_id, fecha, en_promocion, permitir_promocion_faltante=False):
        if en_promocion is None and permitir_promocion_faltante:
            en_promocion = np.nan
        elif type(en_promocion) is not int or en_promocion < 0:
            raise ValueError("Promoción debe ser un entero no negativo conocido en D")
        c = self.contexto
        tienda = c.tiendas[tienda_id]
        apertura = date.fromisoformat(tienda["fecha_apertura"])
        if fecha < apertura:
            raise ValueError("Fecha anterior a apertura")
        historia = self.historial.get((tienda_id, familia_id), {})
        indice_tienda = sorted(c.tiendas).index(tienda_id)
        angulo = 2 * pi * fecha.timetuple().tm_yday / (366 if calendar.isleap(fecha.year) else 365)
        valores = [indice_tienda, c.familias[familia_id], c.ciudades[tienda["ciudad"]], c.formatos[tienda["tipo"]],
                   (fecha - apertura).days, fecha.year, fecha.month, fecha.day, fecha.weekday(), sin(angulo), cos(angulo),
                   int(fecha.day == calendar.monthrange(fecha.year, fecha.month)[1]), int(fecha.day == 15), en_promocion]
        for ambito in ("nacional", tienda["ciudad"]):
            valores.extend(int(tipo in c.eventos.get((fecha, ambito), set())) for tipo in TIPOS_EVENTO)
        valores.extend(historia.get(fecha - timedelta(days=d), np.nan) for d in (1, 7, 14, 28))
        for dias in (7, 28, 56):
            muestra = [historia[fecha - timedelta(days=d)] for d in range(1, dias + 1) if fecha - timedelta(days=d) in historia]
            valores.extend([float(np.mean(muestra)) if muestra else np.nan,
                            float(np.std(muestra)) if muestra else np.nan, len(muestra)])
        semanal = [historia[fecha - timedelta(days=d)] for d in range(7, 57, 7) if fecha - timedelta(days=d) in historia]
        valores.append(float(np.mean(semanal)) if semanal else np.nan)
        return valores


def construir_matriz(directorio):
    """Lee promociones de D del histórico, como las conocería la solicitud de D."""
    contexto = Contexto.cargar(directorio)
    with (Path(directorio) / "historico_ventas.csv").open(encoding="utf-8-sig", newline="") as archivo:
        filas = sorted(csv.DictReader(archivo), key=lambda f: (f["fecha"], int(f["tienda_id"]), f["familia_id"]))
    engine = FeaturesCausales(contexto)
    x, ventas = [], []
    for f in filas:
        venta = Venta(date.fromisoformat(f["fecha"]), int(f["tienda_id"]), f["familia_id"], int(f["ventas"]))
        promo = int(f["en_promocion"]) if f["en_promocion"].strip() else None
        x.append(engine.fila(venta.tienda_id, venta.familia_id, venta.fecha, promo, permitir_promocion_faltante=True))
        ventas.append(venta)
        # Cada serie tiene como máximo una fila diaria; fila() solo consulta fechas < D.
        engine.agregar([venta])
    return np.asarray(x, dtype=float), ventas, contexto
