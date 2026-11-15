"""Baseline semanal con distribución empírica reciente, sin librerías de ML."""

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from math import ceil, isfinite


@dataclass(frozen=True)
class Venta:
    fecha: date
    tienda_id: int
    familia_id: str
    ventas: int

    def __post_init__(self):
        if type(self.ventas) is not int or self.ventas < 0:
            raise ValueError("ventas debe ser un entero no negativo")
        if type(self.tienda_id) is not int or self.tienda_id <= 0 or not self.familia_id:
            raise ValueError("Tienda o familia inválida")


@dataclass(frozen=True)
class Costos:
    faltante: float
    sobrante: float

    def __post_init__(self):
        if not all(isfinite(v) and v >= 0 for v in (self.faltante, self.sobrante)):
            raise ValueError("Costos deben ser finitos y no negativos")
        if self.faltante + self.sobrante <= 0:
            raise ValueError("Al menos un costo debe ser positivo")

    @property
    def cuantil(self):
        faltante = Fraction(str(self.faltante))
        return faltante / (faltante + Fraction(str(self.sobrante)))


def costo_negocio(real: int, sugerido: int, costos: Costos) -> float:
    if real < 0 or type(sugerido) is not int or sugerido < 0:
        raise ValueError("Real y sugerido deben ser no negativos; sugerido entero")
    return costos.faltante * max(real - sugerido, 0) + costos.sobrante * max(sugerido - real, 0)


def cantidad_optima(muestra: list[int], costos: Costos) -> int:
    """Cuantil empírico que minimiza el costo medio de la muestra, sin interpolar."""
    if not muestra or any(type(v) is not int or v < 0 for v in muestra):
        raise ValueError("Se requiere una muestra no vacía de enteros no negativos")
    ordenada = sorted(muestra)
    # Con faltante cero, el mínimo no negativo 0 también es óptimo.
    if costos.faltante == 0:
        return 0
    indice = max(0, ceil(len(ordenada) * costos.cuantil) - 1)
    return ordenada[indice]


@dataclass(frozen=True)
class Pronostico:
    venta_esperada: float
    cantidad_sugerida: int
    muestras: int
    estrategia: str


class BaselineSemanal:
    def __init__(self, historial, costos: dict[str, Costos], ventana_dias: int = 56):
        if type(ventana_dias) is not int or ventana_dias < 7:
            raise ValueError("La ventana debe ser un entero de al menos 7 días")
        self.ventana_dias = ventana_dias
        self.costos = dict(costos)
        self._series = {}
        self.agregar(historial)

    def agregar(self, observaciones):
        # Validación completa antes de modificar el estado.
        nuevas = list(observaciones)
        claves = set()
        for venta in nuevas:
            clave = (venta.tienda_id, venta.familia_id)
            fechas = self._series.get(clave, ([], []))[0]
            posicion = bisect_left(fechas, venta.fecha)
            if (clave, venta.fecha) in claves or (posicion < len(fechas) and fechas[posicion] == venta.fecha):
                raise ValueError("Observación duplicada: reconciliar antes de modelar")
            if venta.familia_id not in self.costos:
                raise ValueError(f"Sin costos para {venta.familia_id}")
            claves.add((clave, venta.fecha))
        for venta in nuevas:
            fechas, valores = self._series.setdefault((venta.tienda_id, venta.familia_id), ([], []))
            posicion = bisect_left(fechas, venta.fecha)
            fechas.insert(posicion, venta.fecha)
            valores.insert(posicion, venta.ventas)

    def predecir(self, tienda_id: int, familia_id: str, fecha: date) -> Pronostico:
        fechas, valores = self._series.get((tienda_id, familia_id), ([], []))
        inicio = bisect_left(fechas, fecha - timedelta(days=self.ventana_dias))
        fin = bisect_left(fechas, fecha)  # Excluye día D y todo futuro, incluso si se cargaron.
        semanal = [valores[i] for i in range(inicio, fin) if fechas[i].weekday() == fecha.weekday()]
        muestra = semanal or valores[inicio:fin]
        if not muestra:
            raise ValueError(f"Sin historial anterior reciente para {tienda_id}/{familia_id}")
        return Pronostico(sum(muestra) / len(muestra), cantidad_optima(muestra, self.costos[familia_id]),
                          len(muestra), "mismo_dia_semana" if semanal else "historial_reciente")
