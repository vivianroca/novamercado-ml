# Contexto para trabajar en NovaMercado

## Fuente y alcance

El contrato se contrasta con `Laboratorio_2_PD_26_c.pdf`; requisitos y evidencias se controlan en `PLAN_LABORATORIO_2_NOVAMERCADO.md`. La implementación vigente abarca FastAPI, PostgreSQL del producto, MLflow 3.17.2, Airflow 3.3.2 y arranque con Docker Compose. No trates notas históricas del plan como estado actual; revisa la matriz y las evidencias más recientes.

## Límites obligatorios

- Conserva literalmente rutas, campos y códigos HTTP del PDF. Consulta `/openapi.json` y pruebas antes de modificar contratos.
- Mantén limpieza en `app/calidad/normalizacion.py`, esquemas en `app/schemas/`, adaptadores HTTP en `app/api/`, persistencia en `app/db/` y servicios en `app/servicios/`.
- `data/` contiene insumos privados: nunca versionarlos ni copiarlos a imágenes. `.env` contiene credenciales: no leerlo en comandos que impriman contenido, versionarlo ni incluirlo en evidencias.
- PostgreSQL de producto (`product-db`) y metastore Airflow (`airflow-db`) son independientes. Servicio MLflow se llama `mlflow`.
- Features para la fecha D solo pueden usar observaciones anteriores a D. Las fechas son simuladas; no aplicar reglas basadas en el reloj real.
- Modelo servido = snapshot cargado; ante caída de MLflow conservarlo. Actualización consulta el alias cada 30 s como máximo.
- Un único escritor debe cambiar `champion`. Las pruebas de promoción no deben tocar el tracking principal.
- No declares una fila de la matriz verificada sin prueba/evidencia referenciable. Distingue unit tests, integración, y Compose aislado.

## Estructura actual

- `app/`: FastAPI, validación, API, bootstrap y conexiones/esquema PostgreSQL.
- `ml/`: carga de datos, features causales, baseline, HGB, evaluación, registro y promoción.
- `airflow/dags/reentrenamiento.py`: DAG manual; `airflow/Dockerfile` separa dependencias ML del SDK Airflow.
- `tests/`: pytest. `tests/conftest.py` reemplaza tracking heredado por stores temporales y bloquea clientes MLflow externos. `tests/test_persistencia.py` usa `TEST_PRODUCT_DB_DSN` solo para un servidor de pruebas exclusivo.
- `scripts/verificar_integral.py`: aceptación Compose opt-in; inicia bootstrap/reentrenamiento reales en un proyecto nuevo. No ejecutarlo como parte de pytest ni dirigir sus servicios al tracking principal.
- `evidencias/`: reportes de pruebas y ejecución, nunca credenciales.

## Desarrollo y verificación

Python 3.12 principal: `.venv/bin/python`; SDK Airflow de pruebas: `.venv-airflow/bin/python`. Instalación descrita en README. Suite sin entrenamientos de DAG:

```sh
.venv/bin/python -m pytest tests -q -k 'not dag_airflow_real'
```

Las pruebas con `TEST_PRODUCT_DB_DSN` crean y eliminan bases aleatorias en el servidor indicado. Usar únicamente servidor temporal/descartable. Los dos tests `dag_airflow_real` entrenan datos sintéticos en stores aislados, así que excluirlos cuando no se esté verificando esa ejecución.

No construir/arrancar servicios o ejecutar runners de entrenamiento salvo solicitud del usuario. Las pruebas unitarias, lectura de archivos y validación estática no necesitan Docker. No borrar volúmenes ni limpiar runs para resolver una prueba; primero aislar dependencias.

## Estado probado y límites conocidos

Evidencias recientes: Fase 7 aislada verifica Registry vacío, arranque, reentrenamiento, promoción efectiva 1→2, refresco de API, caída/retorno de MLflow y persistencia. Fase 8.1 documenta R02–R05, R07, R10–R12 y R17. La matriz sigue siendo la autoridad para requisitos pendientes: clon limpio, tag/remoto/entrega y evidencias de API aún pueden quedar abiertos aunque el código exista.
