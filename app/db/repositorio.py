"""Escrituras atómicas con psycopg. Cada llamada confirma al cerrar su transacción."""

from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from app.db.conexion import conectar_producto
from ml.baseline import Venta
from app.servicios.interfaces import ServicioNoDisponible


class RepositorioProducto:
    def __init__(self, conectar=conectar_producto):
        self.conectar = conectar

    def leer_observaciones(self, tienda_id, desde, hasta, familias):
        """Solo pasado solicitado; las correcciones vigentes prevalecen sobre CSV."""
        try:
            with self.conectar() as conexion:
                filas = conexion.execute(
                    """SELECT fecha, tienda_id, familia_id, ventas
                       FROM novamercado.observaciones
                       WHERE tienda_id=%s AND fecha >= %s AND fecha < %s
                         AND familia_id=ANY(%s)
                       ORDER BY fecha, familia_id""",
                    (tienda_id, desde, hasta, list(familias)),
                ).fetchall()
            return [Venta(*fila) for fila in filas]
        except psycopg.Error as error:
            raise ServicioNoDisponible("No se pudieron consultar las observaciones del producto") from error

    @staticmethod
    def _solicitud(conexion, tipo, original, solicitud, calidad):
        identificador = uuid4()
        conexion.execute(
            """INSERT INTO novamercado.solicitudes
               (id, tipo, tienda_id, fecha, original, canonica, calidad_estado)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (identificador, tipo, solicitud.tienda_id, solicitud.fecha,
             Jsonb(original), Jsonb(solicitud.model_dump(mode="json")), calidad.estado),
        )
        for orden, accion in enumerate(calidad.observaciones):
            conexion.execute(
                """INSERT INTO novamercado.acciones_calidad
                   (solicitud_id, orden, campo, accion, detalle) VALUES (%s,%s,%s,%s,%s)""",
                (identificador, orden, accion.campo, accion.accion, accion.detalle),
            )
        return identificador

    def guardar(self, original, solicitud, calidad) -> int:
        """Upsert por tienda/fecha/familia; solo cambios reales cuentan y generan historial."""
        try:
            with self.conectar() as conexion:
                identificador = self._solicitud(conexion, "observaciones", original, solicitud, calidad)
                guardados = 0
                for item in sorted(solicitud.ventas, key=lambda v: v.familia_id):
                    parametros = (solicitud.tienda_id, solicitud.fecha, item.familia_id,
                                  item.ventas, identificador)
                    cambio = conexion.execute(
                        """INSERT INTO novamercado.observaciones AS actual
                           (tienda_id, fecha, familia_id, ventas, solicitud_id)
                           VALUES (%s,%s,%s,%s,%s)
                           ON CONFLICT (tienda_id, fecha, familia_id) DO UPDATE
                           SET ventas=EXCLUDED.ventas, solicitud_id=EXCLUDED.solicitud_id,
                               actualizada_en=now()
                           WHERE actual.ventas IS DISTINCT FROM EXCLUDED.ventas
                           RETURNING familia_id""", parametros,
                    ).fetchone()
                    if cambio:
                        conexion.execute(
                            """INSERT INTO novamercado.historial_observaciones
                               (tienda_id, fecha, familia_id, ventas, solicitud_id)
                               VALUES (%s,%s,%s,%s,%s)""", parametros,
                        )
                        guardados += 1
            return guardados  # Solo tras commit exitoso.
        except psycopg.Error as error:
            raise ServicioNoDisponible("No se pudo confirmar el registro de observaciones") from error

    def guardar_prediccion(self, original, solicitud, calidad, resultado):
        esperadas = {f.familia_id for f in solicitud.familias}
        recibidas = [p.familia_id for p in resultado.predicciones]
        if set(recibidas) != esperadas or len(recibidas) != len(esperadas):
            raise ValueError("Las predicciones deben corresponder a las familias solicitadas")
        try:
            with self.conectar() as conexion:
                identificador = self._solicitud(conexion, "prediccion", original, solicitud, calidad)
                for item in resultado.predicciones:
                    conexion.execute(
                        """INSERT INTO novamercado.predicciones
                           (solicitud_id, familia_id, version_modelo, venta_esperada, cantidad_sugerida)
                           VALUES (%s,%s,%s,%s,%s)""",
                        (identificador, item.familia_id, resultado.version_modelo,
                         item.venta_esperada, item.cantidad_sugerida),
                    )
            return identificador
        except psycopg.Error as error:
            raise ServicioNoDisponible("No se pudo confirmar el registro de la predicción") from error
