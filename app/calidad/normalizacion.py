"""Normalización explícita, sin HTTP, persistencia ni dependencias de ML."""

import csv
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from pydantic import ValidationError

from app.schemas.solicitudes import (
    AccionCalidad, Calidad, SolicitudObservaciones, SolicitudPrediccion,
)


class SolicitudInvalida(ValueError):
    """El adaptador HTTP debe responder 422 con este detail."""

    status_code = 422

    def __init__(self, campo: str, motivo: str):
        self.detail = f"{campo}: {motivo}"
        super().__init__(self.detail)


def _token(texto: str) -> str:
    texto = "".join(c for c in unicodedata.normalize("NFKD", texto.casefold())
                    if not unicodedata.combining(c))
    return re.sub(r"[\s_]+", "_", texto.strip())


@dataclass(frozen=True)
class Catalogos:
    tiendas: frozenset[int]
    familias: frozenset[str]
    alias_familias: dict[str, str]

    @classmethod
    def desde_directorio(cls, directorio: str | Path):
        def leer(nombre):
            with (Path(directorio) / nombre).open(encoding="utf-8-sig", newline="") as archivo:
                return list(csv.DictReader(archivo))

        tiendas = frozenset(int(r["tienda_id"]) for r in leer("tiendas.csv"))
        filas = leer("familias.csv")
        alias = {}
        for fila in filas:
            for nombre in (fila["familia_id"], fila["nombre"]):
                clave = _token(nombre)
                if clave in alias and alias[clave] != fila["familia_id"]:
                    raise ValueError(f"Alias ambiguo en catálogo: {nombre}")
                alias[clave] = fila["familia_id"]
        return cls(tiendas, frozenset(r["familia_id"] for r in filas), alias)


def _entero(valor, campo):
    if type(valor) is int:
        numero = valor
    elif type(valor) is float and math.isfinite(valor) and valor.is_integer():
        numero = int(valor)
    elif isinstance(valor, str) and re.fullmatch(r"[0-9]+", valor.strip()):
        numero = int(valor.strip())
    elif isinstance(valor, str) and re.fullmatch(r"[0-9]+[.,]0+", valor.strip()):
        # 50,0 es inequívocamente integral; 1,000 admite dos lecturas.
        if "," in valor and len(valor.strip().split(",")[1]) == 3:
            raise SolicitudInvalida(campo, "separador numérico ambiguo")
        numero = int(re.split(r"[.,]", valor.strip())[0])
    else:
        raise SolicitudInvalida(campo, "se requiere un entero no negativo; formato ambiguo o inválido")
    if numero < 0:
        raise SolicitudInvalida(campo, "no se admiten valores negativos")
    return numero


def _fecha(valor):
    if not isinstance(valor, str):
        raise SolicitudInvalida("fecha", "se requiere una fecha de texto")
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor):
            return date.fromisoformat(valor)
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}", valor):
            return datetime.strptime(valor, "%d/%m/%Y").date()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}T00:00:00", valor):
            return date.fromisoformat(valor[:10])
    except ValueError:
        pass
    raise SolicitudInvalida("fecha", "fecha inválida; usar AAAA-MM-DD, DD/MM/AAAA o ISO a medianoche")


def _normalizar(entrada, catalogos, observacion):
    acciones = []

    def reparar(campo, detalle):
        acciones.append(AccionCalidad(campo=campo, accion="reparar", detalle=detalle))

    if not isinstance(entrada, dict):
        raise SolicitudInvalida("solicitud", "se requiere un objeto")
    datos = dict(entrada)
    if "tienda" in datos:
        if "tienda_id" in datos:
            raise SolicitudInvalida("tienda", "no enviar tienda y tienda_id simultáneamente")
        datos["tienda_id"] = datos.pop("tienda")
        reparar("tienda_id", "Se renombró tienda a tienda_id")
    lista, medida = ("ventas", "ventas") if observacion else ("familias", "en_promocion")
    requeridos = {"tienda_id", "fecha", lista}
    if set(datos) != requeridos:
        raise SolicitudInvalida("solicitud", f"campos faltantes: {sorted(requeridos-set(datos))}; desconocidos: {sorted(set(datos)-requeridos)}")
    original = datos["tienda_id"]
    valor = original
    if isinstance(valor, str) and re.fullmatch(r"T[0-9]+", valor.strip(), re.I):
        valor = valor.strip()[1:]
    tienda = _entero(valor, "tienda_id")
    if tienda not in catalogos.tiendas:
        raise SolicitudInvalida("tienda_id", "tienda desconocida")
    if type(original) is not int or original != tienda:
        reparar("tienda_id", f"Se interpretó {original!r} como {tienda}")
    fecha = _fecha(datos["fecha"])
    if datos["fecha"] != fecha.isoformat():
        reparar("fecha", f"Se normalizó a {fecha.isoformat()}")
    if not isinstance(datos[lista], list) or not datos[lista]:
        raise SolicitudInvalida(lista, "se requiere una lista no vacía")
    items, vistos = [], {}
    for i, item in enumerate(datos[lista]):
        campo = f"{lista}[{i}]"
        if not isinstance(item, dict) or set(item) != {"familia_id", medida}:
            raise SolicitudInvalida(campo, f"se requieren exclusivamente familia_id y {medida}")
        nombre = item["familia_id"]
        familia = catalogos.alias_familias.get(_token(nombre)) if isinstance(nombre, str) else None
        if familia not in catalogos.familias:
            raise SolicitudInvalida(f"{campo}.familia_id", "familia desconocida")
        if nombre != familia:
            reparar(f"{campo}.familia_id", f"Se interpretó {nombre!r} como {familia!r}")
        numero = _entero(item[medida], f"{campo}.{medida}")
        if type(item[medida]) is not int:
            reparar(f"{campo}.{medida}", f"Se interpretó {item[medida]!r} como {numero}")
        if familia in vistos:
            if vistos[familia] != numero:
                raise SolicitudInvalida(campo, "familia duplicada con valores contradictorios")
            reparar(campo, "Se eliminó una repetición idéntica")
            continue
        vistos[familia] = numero
        items.append({"familia_id": familia, medida: numero})
    if not observacion and (faltantes := catalogos.familias - vistos.keys()):
        acciones.append(AccionCalidad(campo=lista, accion="advertir", detalle=
            f"Solicitud parcial: solo se pronosticarán las familias recibidas; faltan {', '.join(sorted(faltantes))}. No se imputan promociones."))
    modelo = SolicitudObservaciones if observacion else SolicitudPrediccion
    try:
        solicitud = modelo.model_validate({"tienda_id": tienda, "fecha": fecha, lista: items})
    except ValidationError as error:
        raise SolicitudInvalida("solicitud", str(error)) from error
    estado = "advertencia" if any(a.accion == "advertir" for a in acciones) else "corregido" if acciones else "ok"
    return solicitud, Calidad(estado=estado, observaciones=acciones)


def normalizar_prediccion(entrada, catalogos: Catalogos) -> tuple[SolicitudPrediccion, Calidad]:
    return _normalizar(entrada, catalogos, False)


def normalizar_observaciones(entrada, catalogos: Catalogos) -> tuple[SolicitudObservaciones, Calidad]:
    return _normalizar(entrada, catalogos, True)
