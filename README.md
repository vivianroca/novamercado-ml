# NovaMercado ML

Fase 6: esquemas, normalización, persistencia PostgreSQL, baseline y HGB con
champion integrado a POST `/v1/prediccion` y DAG manual de reentrenamiento.
Incluye endpoints administrativos, salud/modelo y bootstrap automático idempotente.
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
La API carga el champion desde Registry; el DAG manual reutiliza este entrenamiento.

Evaluar una versión existente sin entrenar:

```sh
.venv/bin/python -m ml.promocion --version 1 --tracking-uri http://127.0.0.1:5001
.venv/bin/python -m pytest tests/test_promocion.py -q
```

Ejecutar promociones con un único escritor. Para cambiar el periodo o los datos
se requiere reevaluar el champion en ese mismo periodo antes de compararlo.

Airflow **3.3.2**: DAG `novamercado_reentrenamiento` en `airflow/dags/reentrenamiento.py`.
Dos tareas secuenciales: `entrenar_y_evaluar` y `decidir_champion`. Sin cron ni
catchup, un run activo, cero reintentos y límite global de 10 minutos. El snapshot
reconcilia histórico + observaciones PostgreSQL por tienda/fecha/familia, con DB
prioritaria. Para filas nuevas recupera promociones de la última solicitud
canónica disponible; si faltan usa NaN, sin inventar cero. El periodo de validación
son los últimos 56 días observados, con calibración anterior de 28 días.

Antes de decidir, reevalúa el champion congelado sobre exactamente los mismos
datos/fechas del candidato. No modifica sus métricas históricas. La promoción
mantiene los dos artefactos de auditoría y agrega `evaluacion/champion_reevaluado.json`.
Si falla entrenamiento no se ejecuta promoción; empate/no mejora conserva vigente.

Compose usa imagen propia basada en `apache/airflow:3.3.2-python3.12`, API server,
scheduler LocalExecutor y dag-processor, con metastore PostgreSQL independiente.
La imagen instala ML en un virtualenv separado para evitar conflictos con el SDK.
`airflow-init` migra solo el metastore y prepara SimpleAuth desde `.env` en un
volumen de credenciales; no copia datos ni secretos a la imagen. `airflow-work`
comparte manifiestos entre tareas; no se pasan datasets por XCom.

Una vez construido y levantado el stack, disparar manualmente:

```sh
docker compose exec airflow-scheduler airflow dags trigger novamercado_reentrenamiento
```

Se puede indicar `fecha_fin` simulada en la configuración del run; no se usa el
reloj real para recortar ventas.

La API expone `POST /admin/reentrenar` sin cuerpo: devuelve 202 con `id`
confirmado por Airflow, o 503 si no puede confirmarlo. Autentica mediante JWT
y REST v2 de Airflow 3.3.2; activa el DAG si está pausado. Ante timeout del
trigger consulta el mismo ID sin repetir el POST.
`GET /admin/reentrenar/{id}` devuelve 200 con `estado: en_curso` o, al terminar,
`estado`, `promovido`, `version` y `motivo`. ID desconocido devuelve 404;
Airflow inaccesible o resultado no verificable devuelve 503.

Una tercera tarea, `finalizar_reentrenamiento`, guarda el resultado en XCom,
incluida la versión vigente al terminar. Una consulta posterior no sustituye esa
versión por el alias actual. El finalizador conserva el fallo del DAG ante errores
previos. Si no puede verificar la versión, la consulta responde 503.
Configurar `AIRFLOW_BASE_URL`, `AIRFLOW_USER` y `AIRFLOW_PASSWORD` (o las variables
`AIRFLOW_ADMIN_USER`/`AIRFLOW_ADMIN_PASSWORD` locales); Compose utiliza la URL interna.
Pytest bloquea el cliente real de Airflow y requiere transporte simulado.

Pruebas con SDK real, sin construir ni levantar contenedores Airflow:

```sh
python3.12 -m venv .venv-airflow
.venv-airflow/bin/python -m pip install -r airflow/requirements-test.txt
.venv/bin/python -m pytest tests -q
```

Las pruebas de DAG ejecutado requieren también `TEST_PRODUCT_DB_DSN` exclusivo
de pruebas. Usan `dag.test()` de Airflow 3.3.2, metastore SQLite temporal y el
tracking MLflow aislado de pytest. Sin `.venv-airflow` se omiten esas pruebas SDK.
La imagen y los servicios de Airflow se construyeron/levantaron con Compose:
UI en `http://127.0.0.1:8080`, DAG registrado sin errores y pausado, cero ejecuciones.
Acceso con `AIRFLOW_ADMIN_USER` y `AIRFLOW_ADMIN_PASSWORD` de `.env`.
Evidencia: `evidencias/airflow_arranque.json`. El arranque completo del producto
y la ejecución del DAG dentro de esos contenedores siguen pendientes.

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


### Modelo y salud

`GET /modelo` devuelve `nombre`, `alias` y `version` (texto) del snapshot cargado,
no una nueva resolución del alias. Sin modelo responde 503. La carga inicial
comienza en segundo plano al arrancar FastAPI; el refresco consulta cada 30 s
y reemplaza el snapshot completo solo tras cargar y validar el candidato.
`MODEL_REFRESH_SECONDS` admite valores positivos de hasta 30 s.

`GET /health` responde 200 `estado: ok` cuando hay modelo y funcionan PostgreSQL
del producto, MLflow y Airflow (metastore, scheduler y dag-processor). Ante fallo
devuelve 200 `estado: degradado` con `motivo`; sin modelo devuelve 503. Las sondas
son de solo lectura, paralelas y sin caché: HTTP timeout 3 s, conexión DB 5 s
y sentencia DB 3 s. No se comprueba solo el HTTP 200 de Airflow: sus componentes
deben indicar `healthy`. Una carga/refresco fallido también degrada la salud.

La caída de MLflow conserva el modelo y las predicciones. La recuperación se
reconoce al responder las sondas y completarse el siguiente refresco. Las pruebas
usan fuentes y dependencias simuladas; incluyen el intervalo real de 30 s para
verificar cambio de versión sin reinicio en menos de 2 minutos. Los tiempos
contemplan servicios y artefactos accesibles; no sustituyen la prueba del stack
completo desde volúmenes vacíos (medición del arranque limpio pendiente).


### Arranque automático y reinicios

1. Colocar `tiendas.csv`, `familias.csv`, `costos.csv`, `feriados.csv` e
   `historico_ventas.csv` en `data/` (o ajustar `DATA_DIR`). Los insumos se montan
   en solo lectura y no se copian a imágenes ni se convierten en observaciones.
2. Copiar `.env.example` a `.env` y completar credenciales y claves de Airflow.
3. Ejecutar `docker compose up --build -d`. En arranques posteriores basta
   `docker compose up -d`. La API escucha en `http://127.0.0.1:8000`.

`product-init` espera PostgreSQL y MLflow saludables, aplica el esquema de forma
idempotente también sobre volúmenes existentes y consulta el champion. Si existe
y está READY, lo conserva sin cargar de nuevo el histórico ni entrenar. Si falta,
valida/carga los CSV y usa el entrenamiento existente con validación en los
últimos 56 días del histórico, sin utilizar el reloj del sistema. Registra el
candidato y aplica la política de promoción existente. Un candidato rechazado
o un error del Registry no se convierten en un modelo ficticio: el inicializador
falla y la API no arranca. Revisar `docker compose logs product-init`.

El checkpoint del candidato vive en `model-cache`, compartido con la API. Si falla
la promoción, el siguiente arranque retoma el candidato sin ajustarlo otra vez.
Un bloqueo de archivo serializa inicializadores del mismo volumen; mantener un
único escritor de promociones. Si cambian los CSV durante una inicialización
incompleta se exige revisar ese candidato. Una interrupción antes de guardar el
checkpoint puede dejar un candidato huérfano en MLflow; no se elimina automáticamente.

Compose espera la terminación exitosa de `product-init` y el scheduler de Airflow
antes de iniciar la API. El healthcheck de la API exige `/health` con `estado: ok`.
Datos operativos, metastore, Registry/artefactos y caché usan volúmenes persistentes.
Para detener: `docker compose stop`; para volver: `docker compose up -d`.
`docker compose restart product-db api mlflow` conserva esos volúmenes.

Para comprobar únicamente la reutilización sin permitir entrenamiento:

```sh
docker compose run --rm --no-deps product-init python -m app.bootstrap --solo-reutilizar
```

Verificación de Fase 6: se construyó la imagen y se ejecutó el inicializador en
modo solo reutilizar sobre el champion existente. El primer entrenamiento desde
Registry vacío se prueba con entrenamiento sustituido; quedan pendientes su
medición real y el límite de salud ok en 10 minutos desde volúmenes vacíos.
