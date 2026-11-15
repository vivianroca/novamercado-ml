"""Solo configuración del PostgreSQL del producto; nunca variables de Airflow."""

import os

import psycopg

from app.servicios.interfaces import ServicioNoDisponible


def conectar_producto():
    requeridos = ("PRODUCT_DB_HOST", "PRODUCT_DB_NAME", "PRODUCT_DB_USER", "PRODUCT_DB_PASSWORD")
    if not all(os.environ.get(k) for k in requeridos):
        raise ServicioNoDisponible("PostgreSQL del producto no configurado")
    return psycopg.connect(
        host=os.environ["PRODUCT_DB_HOST"],
        port=os.environ.get("PRODUCT_DB_PORT", "5432"),
        dbname=os.environ["PRODUCT_DB_NAME"],
        user=os.environ["PRODUCT_DB_USER"],
        password=os.environ["PRODUCT_DB_PASSWORD"],
        connect_timeout=5,
    )
