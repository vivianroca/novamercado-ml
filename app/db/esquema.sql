-- Esquema exclusivo del producto. Aplicar en PRODUCT_DB, nunca en Airflow.
CREATE SCHEMA IF NOT EXISTS novamercado;

CREATE TABLE IF NOT EXISTS novamercado.solicitudes (
    id uuid PRIMARY KEY,
    tipo text NOT NULL CHECK (tipo IN ('prediccion', 'observaciones')),
    tienda_id integer NOT NULL CHECK (tienda_id > 0),
    fecha date NOT NULL,
    original jsonb NOT NULL,
    canonica jsonb NOT NULL,
    calidad_estado text NOT NULL CHECK (calidad_estado IN ('ok', 'corregido', 'advertencia')),
    creada_en timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS novamercado.acciones_calidad (
    solicitud_id uuid NOT NULL REFERENCES novamercado.solicitudes(id),
    orden integer NOT NULL CHECK (orden >= 0),
    campo text NOT NULL,
    accion text NOT NULL CHECK (accion IN ('reparar', 'advertir')),
    detalle text NOT NULL,
    PRIMARY KEY (solicitud_id, orden)
);

CREATE TABLE IF NOT EXISTS novamercado.predicciones (
    solicitud_id uuid NOT NULL REFERENCES novamercado.solicitudes(id),
    familia_id text NOT NULL,
    version_modelo text NOT NULL CHECK (length(version_modelo) > 0),
    venta_esperada double precision NOT NULL CHECK (
        venta_esperada >= 0 AND venta_esperada < 'Infinity'::float8),
    cantidad_sugerida bigint NOT NULL CHECK (cantidad_sugerida >= 0),
    PRIMARY KEY (solicitud_id, familia_id)
);

CREATE TABLE IF NOT EXISTS novamercado.observaciones (
    tienda_id integer NOT NULL CHECK (tienda_id > 0),
    fecha date NOT NULL,
    familia_id text NOT NULL,
    ventas bigint NOT NULL CHECK (ventas >= 0),
    solicitud_id uuid NOT NULL REFERENCES novamercado.solicitudes(id),
    actualizada_en timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tienda_id, fecha, familia_id)
);

CREATE TABLE IF NOT EXISTS novamercado.historial_observaciones (
    solicitud_id uuid NOT NULL REFERENCES novamercado.solicitudes(id),
    tienda_id integer NOT NULL,
    fecha date NOT NULL,
    familia_id text NOT NULL,
    ventas bigint NOT NULL CHECK (ventas >= 0),
    registrada_en timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (solicitud_id, familia_id)
);

CREATE INDEX IF NOT EXISTS solicitudes_tienda_fecha
    ON novamercado.solicitudes(tienda_id, fecha);
CREATE INDEX IF NOT EXISTS historial_tienda_fecha
    ON novamercado.historial_observaciones(tienda_id, fecha, familia_id);
