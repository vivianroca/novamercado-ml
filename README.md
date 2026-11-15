# NovaMercado ML

Fase 4: esquemas, normalización, persistencia PostgreSQL, baseline y HGB con
champion integrado a POST `/v1/prediccion`. Aún no hay DAG ni bootstrap automático.
No es un producto listo para evaluar.

El baseline semanal se evalúa de forma independiente; el endpoint sirve el modelo
ejecutable registrado con alias `champion`, sin resultados ficticios.

Evaluación reproducible (sin Docker, DB ni MLflow):

```sh
.venv/bin/python -m ml.evaluacion --data-dir data --inicio 2026-01-04 --fin 2026-02-28
.venv/bin/python -m pytest tests/test_baseline.py -q
```

Resultados agregados en `evidencias/baseline_4_1.json`; políticas y limitaciones
en `DECISIONES.md`. La validación incorpora ventas solo después de pronosticar
su día. Los sugeridos usan cuantiles empíricos según costos por familia.

Registrar el reporte existente en el único experimento `NovaMercado`, sin entrenar:

```sh
docker compose --env-file .env.example up -d --no-deps mlflow
.venv/bin/python -m ml.tracking --tracking-uri http://127.0.0.1:5001
```

Instalar antes las dependencias de `requirements.txt`. Dentro de Compose el URI
es `http://mlflow:5000` (ya configurado); desde el host se usa el puerto 5001.
El comando valida hashes del reporte contra `data/` antes de crear el run.
Registra parámetros, métricas globales/por familia, reporte, configuración,
snapshot del código y linaje de insumos sin subir CSV ni credenciales.
Cada ejecución crea un run nuevo en el mismo experimento. Una subida fallida
queda `FAILED`; no se crean versiones del Registry ni alias/promociones.
La evidencia verificada está en `evidencias/mlflow_baseline.json`.

Servidor y cliente usan **MLflow 3.17.2**. La actualización conservó los volúmenes
de metadata/artefactos y los runs previos; respaldo local en
`.backups/mlflow-antes-3.17.2/` (ignorado por Git y Docker).
Verificación: `evidencias/mlflow_upgrade_3_17_2.json`.

Pruebas de compatibilidad aisladas (sin Docker ni tracking principal):

```sh
.venv/bin/python -m pytest tests/test_mlflow_compatibilidad.py -v
```

Pytest usa tracking/Registry temporales por defecto. Las pruebas HTTP inician un
servidor MLflow local propio con puerto aleatorio, SQLite, artefactos e insumos
sintéticos en el directorio temporal de pytest. No requieren datos, runs o modelos
de NovaMercado ni un servicio MLflow ya activo. El servidor de pruebas se detiene
al terminar; no se eliminan runs ni modelos existentes.

`tests/conftest.py` sustituye las variables MLflow heredadas del shell y bloquea
clientes hacia URIs ajenas a sus stores aislados. No establecer
`TEST_MLFLOW_TRACKING_URI` al servicio principal: ya no se utiliza para seleccionarlo.
Las pruebas de contrato y unitarias no necesitan arrancar el servidor de pruebas.

Entrenamiento manual, comparación y decisión champion (MLflow debe estar activo):

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m ml.entrenamiento --tracking-uri http://127.0.0.1:5001
.venv/bin/python -m pytest tests/test_histgradient.py -q
```

Usa el mismo periodo de 56 días del baseline, con un bloque temporal previo de
28 días para calibrar sugeridos por costos. No usa validación para ajustar pesos
ni sugeridos. La comparación queda en `evidencias/comparacion_histgradient.json`
y en el experimento `NovaMercado`. El modelo ejecutable recibe las 36 columnas de
features, no directamente el JSON del endpoint; generación de variables en
`ml/features.py`. Tras finalizar el run se evalúa la versión con la política de
`DECISIONES.md`: ahorro mínimo 1%, controles técnicos y por familia. Si cumple,
actualiza `champion`; si no, conserva el vigente. Cada evaluación tiene su run
propio con `comparacion_modelos.csv` y `decision_champion.md` en la raíz.
La API carga el champion desde Registry; no hay DAG de reentrenamiento.

Evaluar una versión existente sin entrenar:

```sh
.venv/bin/python -m ml.promocion --version 1 --tracking-uri http://127.0.0.1:5001
.venv/bin/python -m pytest tests/test_promocion.py -q
```

Ejecutar promociones con un único escritor. Para cambiar el periodo o los datos
se requiere reevaluar el champion en ese mismo periodo antes de compararlo.

Los insumos del GES están en `data/`, dentro del proyecto. La ruta es configurable con
`DATA_DIR`; se monta en `/data` en solo lectura y no se copia a las imágenes.
Colocar allí los cinco CSV, `catalogo_errores.md` y la carpeta `ejemplos/`.
Todo su contenido queda excluido de Git salvo `data/.gitkeep`.

Configuración local: copiar `.env.example` a `.env`, sustituir los marcadores de
contraseñas y claves. Para Fernet usar una clave válida generada con
`cryptography.fernet.Fernet.generate_key()`. Para las contraseñas del metastore
usar caracteres seguros para URI (por ejemplo, hexadecimales).

Validación estática, sin construir ni arrancar contenedores:

```sh
docker compose --env-file .env.example config --quiet
```

El archivo de ejemplo sirve para validar la estructura; sus marcadores no sirven
para arrancar. El arranque completo del producto aún no está verificado.

Servicios: API en 8000, MLflow en 5001 y Airflow web en 8080, publicados solo en
localhost. Hay dos PostgreSQL independientes, sin puertos publicados. Los datos
de ambas bases, metadata/artefactos de MLflow, logs de Airflow y caché del modelo
usan volúmenes persistentes. `airflow-init` prepara únicamente el metastore y su
usuario administrativo; no es el bootstrap del producto, pendiente de Fase 6.

Código: `app/` (API, esquemas, calidad, servicios y DB), `ml/`, `airflow/dags/`,
`tests/` y `evidencias/`. Los comandos de arranque y las pruebas integradas se
documentarán y verificarán al implementar las fases correspondientes.

Pruebas locales de normalización (Python 3.12, sin Docker ni MLflow):

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
```

Las políticas están en `DECISIONES.md`. Las pruebas sintéticas no necesitan datos
GES; con los datos locales también se verifican los ejemplos docentes.

Los endpoints devuelven 200 con el contrato del PDF cuando reciben resultados
de proveedores configurados y 422 con `detail` ante solicitudes inválidas.
POST `/v1/prediccion` carga el champion de `MODEL_NAME` desde MLflow, construye
variables con los CSV y observaciones del producto, devuelve predicciones reales
y la versión efectivamente utilizada, y confirma su registro antes de responder.
Si no hay modelo cargado o la DB no puede confirmar el registro, responde 503.
Observaciones usan PostgreSQL del producto; si no está configurado o el guardado
no se puede confirmar, responden 503. No se inventan predicciones ni registros.

La API usa `MLFLOW_TRACKING_URI`, `MODEL_NAME` (por defecto
`novamercado-histgradientboosting`), `MODEL_CACHE_DIR` y `MODEL_REFRESH_SECONDS`
(30 segundos). En Compose estas variables están configuradas. Desde el host,
exportar también las variables `PRODUCT_DB_*` contra una base inicializada y
`DATA_DIR`; los módulos no leen `.env` automáticamente. Ejecutar con
`.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`.

El primer pronóstico válido carga el modelo. Las solicitudes posteriores usan
el snapshot en memoria, sin consultar ni descargar MLflow por solicitud. Un hilo
refresca el alias y solo intercambia modelo/versión tras una carga válida completa.
Si MLflow falla o el artefacto nuevo es incompatible, conserva el anterior.
La DB sigue siendo necesaria para leer observaciones y persistir predicciones.
La caché en disco guarda descargas; el arranque sin acceso a Registry todavía no
tiene recuperación offline. Las fechas deben ser posteriores al corte de ajuste/
calibración del modelo; no se consulta el reloj real para validarlas.

Evidencia de serving real y fallo de transporte simulado:
`evidencias/prediccion_champion.json`. Pytest usa modelos ejecutables entrenados
con datos sintéticos en su tracking aislado; no escribe en NovaMercado principal.

Interfaces en `app/servicios/interfaces.py`; sustituir `obtener_predictor`,
`obtener_registro` y, opcionalmente, `obtener_catalogos` mediante
`app.dependency_overrides`, como en `tests/test_endpoints.py`.

Persistencia: `app/db/esquema.sql` crea el esquema `novamercado`, solicitudes
originales/canónicas, acciones de calidad, predicciones versionadas y observaciones
con historial. Compose monta este SQL únicamente en `product-db`; PostgreSQL lo
aplica automáticamente en el primer arranque con volumen vacío. Para una base
existente, ejecutar explícitamente `python -m app.db.migrar` con variables
`PRODUCT_DB_HOST`, `PRODUCT_DB_NAME`, `PRODUCT_DB_USER`, `PRODUCT_DB_PASSWORD`
y opcionalmente `PRODUCT_DB_PORT` (5432). Este comando no lee `.env` automáticamente;
las variables deben estar exportadas. La inicialización es transaccional y repetible;
futuros cambios estructurales requerirán nuevas migraciones.

Pruebas de integración: definir `TEST_PRODUCT_DB_DSN` contra un servidor PostgreSQL
**exclusivo de pruebas**, con permiso de crear bases, y ejecutar pytest. Las pruebas
crean una base aleatoria y la eliminan al terminar; no modifican tablas de la base
indicada en el DSN. Sin esta variable se omiten explícitamente las pruebas reales
de DB; las demás se ejecutan sin PostgreSQL ni MLflow. No usar el metastore Airflow.
