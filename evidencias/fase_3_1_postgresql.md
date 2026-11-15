# Verificación de persistencia — Fase 3.1

Entorno: Python 3.12.16, pytest 8.3.5, PostgreSQL `postgres:16.8-bookworm`.
Contenedor temporal exclusivo, con tmpfs en `/var/lib/postgresql/data`, puerto
aleatorio ligado a 127.0.0.1 y credencial aleatoria no registrada. Sin usar o
borrar volúmenes ni datos existentes. El contenedor fue detenido al terminar.

Se ejecutó `.venv/bin/python -m pytest -v` con `TEST_PRODUCT_DB_DSN` definido
solo para el proceso de pruebas. Resultado: **100 passed, 0 skipped, 1 warning
in 0.58s**. La advertencia es una obsolescencia de Starlette/AnyIO.

Las seis pruebas PostgreSQL pasaron:

- Reenvío/corrección: conteos 1, 0, 1, 0; un valor vigente y dos cambios históricos.
- Concurrencia: ocho envíos idénticos; un resultado 1 y siete resultados 0,
  con una observación y un cambio histórico.
- Predicciones repetidas: solicitudes distintas conservan versiones 3 y 4
  (resultados de prueba, sin implementar modelo).
- Rollback: error en el segundo ítem revierte solicitudes, acciones, observaciones
  e historial del lote completo.
- Lote mixto: una observación modificada y otra nueva devuelven 2; reenvío devuelve 0.
- POST `/v1/observaciones` con PostgreSQL: respuestas HTTP 200 con conteos 1, 0,
  2, 0 para inserción, reenvío, lote nuevo + modificado y reenvío del lote.

Las bases aleatorias creadas por los tests se eliminaron dentro del servidor
temporal exclusivo. No se levantó Airflow ni MLflow y no se construyeron imágenes.
La persistencia operativa tras reiniciar el producto sigue pendiente de prueba.

## Conexión real FastAPI → PostgreSQL

Nueva ejecución completa con PostgreSQL temporal aislado: **103 passed, 0 skipped,
1 warning in 0.69s**. Tres pruebas adicionales sin `dependency_overrides` verifican
configuración por `PRODUCT_DB_*`, catálogos por `DATA_DIR` y repositorio real.
Un DSN de Airflow inválido no afecta al producto.

- Observaciones: HTTP 200 y conteos 1, 0, 2, 0. Consulta SQL confirma dos valores
  vigentes, tres cambios históricos y cuatro solicitudes auditadas.
- Predicción sin modelo: HTTP 503 sin escrituras ficticias. Observaciones negativas:
  HTTP 422 sin escrituras.
- Base configurada inexistente: HTTP 503 sin confirmar registros ni guardar solicitud.

El contenedor temporal se detuvo tras la ejecución, sin tocar datos/volúmenes existentes.
