# Decisiones iniciales — Fase 1

- Dos servicios PostgreSQL con volúmenes independientes: producto y metastore.
- Airflow con LocalExecutor y un scheduler, sin Redis ni workers adicionales.
- MLflow usa SQLite para metadata y volumen separado para artefactos servidos
  por HTTP. Evita una tercera base para esta ejecución local; revisar concurrencia
  y recuperación durante las pruebas de operación.
- Imágenes y dependencias directas con versiones exactas. No se ha generado aún
  un lock de dependencias transitivas ni verificado la construcción de imágenes.
- Credenciales externas mediante `.env`, excluido de Git y contexto Docker.
- Insumos locales en `data/`, excluidos de Git y del contexto Docker,
  montados en solo lectura mediante `DATA_DIR` (por defecto `./data`).
- Políticas de calidad, features, modelo, sugeridos y promoción se decidirán en
  sus fases; no hay resultados experimentales todavía.

## Fase 2.1 — Contrato canónico y normalización

Los modelos Pydantic reciben datos canónicos; `app/calidad/normalizacion.py`
normaliza antes de validarlos y devuelve `(solicitud, calidad)`. Los rechazos
generan `SolicitudInvalida` con `status_code=422` y `detail`; la integración HTTP
queda pendiente. No se agregaron endpoints ni acceso a DB/MLflow.

| Caso | Política y justificación |
|---|---|
| E01 | Reparar IDs numéricos como texto o prefijo T; rechazar tiendas desconocidas. |
| E02 | Reparar mayúsculas, acentos, espacios y nombres exactos del catálogo; no usar coincidencia aproximada. |
| E03 | Reparar texto numérico y decimales integrales; rechazar fracciones, booleanos, negativos y no finitos. |
| E04 | Reparar DD/MM/AAAA e ISO con hora exactamente 00:00:00; rechazar fechas imposibles y otros horarios. No consultar reloj real. |
| E05 | Advertir y procesar solo las familias recibidas. No inventar familias ni promociones. Es coherente con solicitudes parciales del anexo. |
| E06 | Rechazar valores contradictorios para la misma familia canónica; eliminar repetición idéntica con reparación informada. |
| E07 | Reparar únicamente el alias conocido tienda → tienda_id; rechazar ambos simultáneamente y campos desconocidos. |
| E08 | Rechazar ventas negativas; no convertir devoluciones en demanda cero. |
| E09 | Aceptar reenvíos sin cambios de normalización. Conteo de guardados e idempotencia en DB pendientes de Fase 3. |
| E10 | Reparar coma decimal inequívoca integral como 50,0; rechazar separadores ambiguos como 1,292 o 1,000. No adivinar miles. |

Reglas generales: rechazar listas vacías, campos requeridos ausentes, elementos
mal estructurados, familias desconocidas y valores nulos. Las observaciones
parciales son válidas: no completar ventas faltantes con ceros. Se conservan
entradas originales sin mutación. Toda conversión aceptada se informa por campo;
una advertencia prevalece sobre reparaciones al calcular `calidad.estado`.
Las familias esperadas son las del catálogo actual (las 12 aparecen en cada tienda
del histórico); un futuro surtido específico requerirá un catálogo de surtidos.

Los catálogos se cargan explícitamente desde un directorio, sin leer datos al
importar. Pruebas sintéticas se ejecutan sin GES; las pruebas adicionales de los
12 JSON docentes requieren los insumos locales, y se omiten si no están disponibles.

## Fase 2.2 — Adaptadores HTTP e interfaces

- POST `/v1/prediccion` y `/v1/observaciones` delegan toda limpieza al módulo de
  normalización y traducen `SolicitudInvalida` a 422 con `detail` explicativo.
  FastAPI devuelve también 422 ante JSON malformado/cuerpo ausente.
- Las respuestas 200 se validan con esquemas Pydantic: versión textual, sugerido
  entero no negativo, calidad y conteo confirmado por el proveedor.
- `Predictor` y `RegistroObservaciones` son protocolos sustituibles. La versión y
  cada valor pronosticado proceden del predictor; se verifica que devuelva exactamente
  las familias solicitadas. El conteo procede únicamente del registro, que recibe
  solicitud original, canónica y calidad. No se implementó almacenamiento.
- Sin proveedor configurado, o ante indisponibilidad explícita, responder 503 con
  `detail`. Es un fallo de disponibilidad, no un rechazo de entrada 422. No devolver
  ceros como predicciones ni `registros_guardados: 0` para fingir una escritura.
- Los dobles de prueba solo están en `tests/`; sus resultados son programados y
  no prueban ML ni idempotencia persistida. Se mantiene pendiente el registro de
  solicitudes/predicciones y su trazabilidad en DB para la Fase 3.
- La aplicación se puede crear aisladamente con `crear_app()`. Los catálogos se
  leen al resolver la dependencia y también pueden sustituirse; no se requiere
  MLflow ni acceder a servicios externos para ejecutar pytest.

## Fase 3.1 — Persistencia del producto

- Esquema PostgreSQL `novamercado` exclusivo de `product-db`. La conexión usa solo
  variables `PRODUCT_DB_*`; no se utiliza ni modifica el metastore de Airflow.
- Se registra cada solicitud aceptada en una fila UUID con entrada original,
  canónica, tienda/fecha y calidad; acciones ordenadas conservan reparaciones y
  advertencias. Se guardan solicitudes repetidas para trazabilidad, sin duplicar
  observaciones ni cambios históricos.
- Predicciones se vinculan a su solicitud, cada una con versión de modelo, venta
  esperada y sugerido. No hay unicidad por tienda/fecha: se admiten varios pronósticos.
  El endpoint solo devuelve 200 después de confirmar su registro.
- Observación vigente: clave primaria `(tienda_id, fecha, familia_id)`. UPSERT con
  `IS DISTINCT FROM` actualiza exclusivamente cambios reales, sin alterar timestamps
  ni linaje del valor vigente ante reenvío idéntico. Cada valor nuevo/modificado
  agrega historial. El conteo se devuelve únicamente después del commit.
- Solicitud, acciones, valores e historial se confirman o revierten juntos. El
  orden por familia reduce riesgo de deadlocks entre lotes concurrentes; PostgreSQL
  serializa conflictos por clave. Un error de DB devuelve 503 sin revelar credenciales.
- El esquema se inicializa con SQL en el primer volumen de producto y existe un
  inicializador explícito repetible para bases existentes. No se aplica DDL en
  cada petición. Cambios futuros de esquema necesitarán migraciones versionadas.
- No se carga aún histórico a DB ni se implementan ML/reentrenamiento. Rechazos
  previos a normalización no se guardan en esta fase. No se declara probada la
  conservación tras reinicio de contenedores hasta ejecutar la prueba operativa.

## Fase 4.1 — Baseline y evaluación temporal

- Baseline independiente de API/DB: por tienda y familia, media de ventas del
  mismo día semanal en los 56 días estrictamente anteriores. Ventana fijada antes
  de evaluar, sin buscar parámetros con ventas de validación. Si faltan días
  semanales, usar ventas recientes de esa misma serie; sin historial, fallar
  explícitamente. No mezclar tiendas ni completar días anteriores a apertura con ceros.
- Sugerido: cuantil empírico de esa misma muestra con nivel
  `costo_faltante / (costo_faltante + costo_sobrante)`, usando rango más cercano
  superior, sin interpolar. Minimiza el costo promedio de la muestra histórica;
  no garantiza óptimo futuro. Es entero y no negativo. Los costos altos de
  sobrante reducen el sugerido y los altos de faltante lo elevan.
- Esta distribución empírica es un supuesto simple de referencia; ocho muestras
  semanales pueden estimar mal cuantiles extremos. No modela promociones ni
  feriados, por lo que esos efectos y el drift son limitaciones esperadas.
- Validación progresiva diaria en 2026-01-04–2026-02-28: inicializar con fechas
  anteriores, pronosticar todas las series de D y solo después incorporar las
  ventas de D para próximos días. Incluso cargado con filas futuras, el baseline
  las excluye con un corte estricto `< D`. Sin particiones aleatorias.
- Se evalúan únicamente observaciones disponibles, sin imputaciones. Duplicados,
  costos inválidos/faltantes y claves desconocidas al cargar CSV se rechazan.
  DB e histórico deberán reconciliarse antes de integrarlos al entrenamiento.
- Métricas: MAE, RMSE, WAPE como proporción (null si suma real cero), costo total
  y medio, y métricas por familia. Comparador de sugerido: media redondeada al
  entero más cercano. Es una comparación de políticas del mismo baseline,
  no evidencia de un modelo ML superior. No usar MAPE debido a ventas cero.
- Resultado agregado en `evidencias/baseline_4_1.json`, con hashes de insumos.
  No se conectó este baseline a la API ni se implementó MLflow/modelo avanzado.

## Integración de tracking MLflow del baseline

- Cliente `mlflow-skinny==3.17.2` alineado con la imagen Compose actual.
  `ml/tracking.py` solo publica el reporte previo y no ejecuta entrenamiento ni
  evaluación. Un único experimento, `NovaMercado`, se reutiliza entre ejecuciones.
- Parámetros: baseline, ventana, cortes temporales, protocolo, política de sugerido
  y variables deliberadamente no usadas. Métricas globales y por familia; WAPE
  indefinido se omite como métrica numérica y queda null en el reporte.
- Artefactos: reporte agregado, configuración, manifest de linaje y código/requirements.
  Inputs nativos de MLflow: cuatro CSV identificados por nombre y digest SHA256
  truncado a 32 caracteres; manifest conserva SHA256 completo. No se suben datos crudos.
- Antes de crear run se verifican hashes de insumos y cortes del reporte. El
  commit, estado dirty y hashes del código reflejan el momento del registro;
  no se presentan como una procedencia de ejecución que el reporte previo no guardó.
- Un fallo de subida marca el run FAILED y se propaga; solo tras todas las subidas
  se marca FINISHED. El URI global se alinea al cliente para resolver
  artefactos HTTP correctamente. No se registra modelo ejecutable, Registry,
  alias, promoción ni predictor de API en esta etapa.

## Actualización MLflow 2.22.0 → 3.17.2

- Se detuvo únicamente MLflow para copiar metadata SQLite y artefactos a
  `.backups/mlflow-antes-3.17.2/`, excluido de Git y Docker. Integridad SQLite
  comprobada; inventario previo incluye parámetros, métricas, tags, inputs y
  hashes de todos los artefactos de los tres runs existentes.
- Se ejecutó `mlflow db upgrade sqlite:////mlflow/metadata/mlflow.db` con la imagen
  3.17.2 antes de reiniciar, conservando ambos volúmenes nombrados. No se borraron
  datos ni runs; para rollback se requiere restaurar el respaldo previo, no asumir
  que una base migrada admite un servidor anterior.
- La lista de hosts de MLflow 3 admite el nombre interno `mlflow:5000` y los
  accesos locales configurados en Compose, sin desactivar el middleware de seguridad.
- Pruebas HTTP verifican tracking, conservación del inventario, UI y Registry:
  modelo de metadata temporal, dos versiones y alias temporal asignado, cambiado
  y eliminado. Se elimina exclusivamente ese modelo de prueba. No se registra
  ni promueve un modelo de producto.
- Guía de migración: https://mlflow.org/docs/latest/self-hosting/migration/

## Fase 4 — HistGradientBoosting y comparación temporal

- Un HGB global (`scikit-learn==1.7.2`, pérdida squared_error), 200 iteraciones,
  learning_rate 0.08, 31 hojas, min_samples_leaf 30, L2 1, semilla 42 y dos hilos.
  Sin búsqueda de hiperparámetros sobre validación ni partición aleatoria interna:
  `early_stopping=False`.
- 36 variables: tienda/familia/ciudad/formato categóricos, edad de tienda, año,
  mes, día, día semanal, ciclo anual seno/coseno, fin de mes/quincena, promoción
  conocida de D, indicadores nacionales y locales de feriado/comercial/pago/medio
  día, rezagos 1/7/14/28 y medias/desviaciones/conteos de 7/28/56 días, más media
  del mismo día semanal. Los feriados locales solo afectan a la ciudad correspondiente.
- Features calculadas con consultas estrictas a fechas anteriores a D. Ventas
  del mismo día o futuras no entran a rezagos ni agregados; faltantes y tienda nueva
  se representan con NaN y conteos, sin inventar ventas previas a apertura.
  Las promociones históricas de D simulan lo que llega en la solicitud de D;
  no se supone que las observaciones futuras las incluyan.
- Ajuste hasta 2025-12-06: 72 972 casos. Calibración temporal separada,
  2025-12-07–2026-01-03: 3 360 casos. Sugerido = predicción no negativa + cuantil
  de residuos de esa calibración por familia, al nivel faltante/(faltante+sobrante),
  redondeado a entero no negativo. No se usan residuos de validación.
- Validación idéntica al baseline: 2026-01-04–2026-02-28, exactamente las mismas
  6 720 claves. Ambos pueden observar días previos de validación, como en la
  operación diaria; HGB conserva los pesos y ajustes congelados. No se reentrena.
- Resultado: HGB mejora MAE, RMSE, WAPE y costo global; costo 197 537.70 frente a
  239 897.90 (17.66% menor). Esto no garantiza generalización a otro periodo o drift;
  la calibración residual por familia supone estabilidad de la distribución de errores.
- Se registra en `NovaMercado` un pyfunc ejecutable que incluye HGB y ajustes de
  inventario, firma de 36 variables, dependencias fijas, código, métricas por familia,
  comparación y linaje SHA256 de los cinco CSV. Registro
  `novamercado-histgradientboosting`, versión 1; sin alias ni promoción.
  Se comprobó descarga/carga y equivalencia del resultado del artefacto.
- No se conecta aún a FastAPI ni se agregan DAGs o reentrenamiento automático.

## Política champion — versión 1

- Cada evaluación crea un run `decision-champion` en `NovaMercado`, independiente
  del run de entrenamiento. En su raíz se guardan siempre
  `comparacion_modelos.csv` (baseline, candidato y, si existe, champion; versiones,
  periodo, casos, MAE/RMSE/WAPE y costos) y `decision_champion.md` (versión candidata,
  vigente anterior/final, criterio, motivo y resultado). No se sobrescribe historia
  de evaluaciones previas. Ante métricas no disponibles, el CSV deja valores vacíos,
  sin inventarlos, y el Markdown explica el error.
- Condiciones previas: versión READY, run FINISHED y activo del experimento
  NovaMercado; métricas del run iguales al reporte, finitas/no negativas, conteos
  y suma de costos por familia coherentes, ajuste y calibración anteriores a
  validación. Candidato y champion requieren mismas fechas, hashes de insumos,
  familias y conteos. Si cambian periodo o insumos, se rechaza la comparación
  hasta reevaluar el champion con los mismos datos; no se comparan costos viejos.
- Promover solo con costo total **al menos 1% menor**, estrictamente inferior,
  MAE/RMSE/WAPE sin regresiones superiores al **5%**, y costo de ninguna familia
  más de **10% peor**. WAPE null solo es comparable con otro null. Umbrales fijados
  antes de aplicar la política: priorizan ahorro con controles técnicos y por
  familia. Sin champion inicial, se usa el baseline de esa misma evaluación.
- Empates, mejora insuficiente o controles incumplidos conservan el vigente.
  Evaluar la versión ya champion no vuelve a promoverla. Si el costo de referencia
  es cero no existe mejora estricta posible.
- Antes de cambiar el alias deben subirse ambos artefactos. Tras cambiarlo se
  vuelve a consultar y se confirma el Markdown. Si falla la confirmación, se
  intenta restituir el alias anterior (o quitar solo el recién creado). Un fallo
  de subida previo nunca cambia el alias. La operación se registra FAILED ante
  errores, y el campo `version` representa el vigente observado al terminar.
- Se serializan invocaciones de esta herramienta en el mismo host y se verifica
  que el alias no cambió antes de escribir. MLflow no ofrece una transacción
  conjunta para alias + artefactos ni CAS del alias: se exige un único escritor
  de promociones. No se afirma exclusión distribuida; si una caída de red impide
  confirmar reversión, se propaga el error y se explicita el estado no confirmado.
- Se usa el alias exacto `champion` en `novamercado-histgradientboosting`. La
  evaluación se invoca tras terminar el entrenamiento, o manualmente sobre una
  versión existente con `python -m ml.promocion --version N`. No implica que la
  API ya use el champion; refresco/serving y Airflow siguen pendientes.

## Aislamiento de MLflow en pytest

- Causa de los runs repetidos: las pruebas HTTP recibían el URI del servicio de
  producto y llamaban a `registrar_baseline()` y `evaluar_champion()` sobre el
  experimento real. La primera función crea un run por registro; la segunda crea
  deliberadamente un run de auditoría por decisión, incluso para rechazos/errores.
  Repetir pytest acumulaba ambos tipos de runs sin entrenar de nuevo el baseline.
- No se cambia el registro/auditoría de ejecuciones reales ni se elimina historia.
  La corrección está en las fixtures: tracking y Registry temporales por prueba;
  servidor HTTP propio por sesión con SQLite y artefactos locales, datos sintéticos
  y modelos de metadata propios. Se conservan nombres de experimento para probar
  el código real, pero en un backend completamente separado del producto.
- Se ignoran URIs e IDs MLflow heredados del shell y se bloquea la construcción de
  clientes hacia un tracking/Registry no autorizado por la fixture. Se comprueba
  explícitamente el bloqueo de `http://127.0.0.1:5001` para ambos tipos de cliente.
- Las pruebas ya no usan IDs de runs, modelo champion o inventario de migración
  del producto; tampoco eliminan modelos como limpieza de la prueba de Registry.
  El servidor aislado se detiene al final. Las pruebas de contrato/unitarias no
  dependen de un MLflow activo; el servidor solo se inicia para integración HTTP.

## Serving del champion en FastAPI

- `obtener_predictor` construye un único servicio por instancia de aplicación,
  sin IO en importaciones ni al validar entradas rechazadas. El primer pronóstico
  válido carga `champion` del Registry; las siguientes solicitudes reutilizan el
  modelo y la versión del mismo snapshot. No hay fallback de predicciones ficticias.
- Se resuelve alias a versión READY, se descarga esa versión numérica explícita,
  metadata y cortes del run, se validan los códigos de tienda/familia/ciudad/formato
  y las 36 features, y se carga el pyfunc localmente. Tracking/Registry se pasan
  explícitamente al cliente y al descargador, sin mutar URIs globales de MLflow.
- Un hilo consulta el alias cada 30 segundos. Las predicciones cargadas no esperan
  el lock de descarga/refresco. El modelo vigente solo cambia después de cargar
  el nuevo completamente; error de red, alias ausente o artefacto incompatible
  conserva el snapshot anterior. Sin snapshot inicial se responde 503. El hilo
  se detiene al cerrar la aplicación. Compose fija timeout HTTP 3s y cero reintentos.
- Features: histórico local indexado una vez; por request se toman solo los 56
  días anteriores y se consulta PostgreSQL de producto para tienda/familias en
  `[D-56, D)`. Observaciones/correcciones vigentes reemplazan el CSV sin duplicar.
  La promoción de D procede exclusivamente de la solicitud. Faltantes siguen NaN.
- Se rechazan con 422 fechas anteriores a apertura o no posteriores al corte de
  entrenamiento/calibración del modelo, evitando usar pesos entrenados con futuro.
  Las fechas son simuladas; no se valida contra el reloj real.
- Una respuesta 200 confirma la persistencia de entrada original/canónica,
  acciones y cada predicción con la versión realmente usada. Si falta DB o falla
  commit, responde 503 aunque exista modelo en memoria. Caída de MLflow no elimina
  la necesidad de contar con PostgreSQL operativo.
- Tests: modelo HGB ejecutable real en tracking aislado, SQL real, coherencia con
  pyfunc, correcciones sobre CSV, exclusión de observaciones D/futuras, continuidad
  con fallo de consulta MLflow, cambio de versión atómico y refresco no bloqueante.
- Comprobación adicional de solo lectura del champion real versión 1, con DB
  temporal: dos familias, predicciones persistidas y repetidas tras fallo de
  transporte simulado; NovaMercado conservó sus 14 runs y el alias sin cambios.
- No se implementa todavía `/health`, Airflow, reentrenamiento ni recuperación
  de arranque offline. Los tiempos operativos de caída/recuperación se medirán
  al integrar salud/operación; la caché de disco no sustituye Registry al arrancar.

## Fase 5 — DAG Airflow 3.3.2

- Dos tareas en orden all_success: entrenar/evaluar sin tocar alias y luego decidir
  champion. Schedule None, catchup False, max_active_runs 1, retries 0; deadline
  global 10 min, tareas limitadas a 8m15s/90s y subprocesos a 480s/75s.
- SDK público `airflow.sdk`, sin leer DB, CSV ni MLflow durante parseo. El código ML
  se invoca con su propio Python para separar dependencias de Airflow y FastAPI/ML.
  Solo versión, run_id y ruta a manifiesto viajan por XCom.
- Snapshot transaccional REPEATABLE READ/READ ONLY del PostgreSQL del producto;
  no se usa metastore Airflow. Observaciones vigentes reemplazan ventas históricas
  por clave y las nuevas se agregan una vez. Insumos originales permanecen intactos.
  Promociones del histórico se conservan; para observaciones nuevas se recupera la
  última solicitud de predicción por familia, ordenada por creada_en/id. Si no hay,
  queda ausente (NaN nativo HGB), no se inventan promociones en observaciones.
- Corte opcional fecha_fin simulada; por defecto última fecha con ventas. Validación
  móvil de 56 días y calibración de 28 días anterior, sin incorporar D/futuro a rezagos.
  Hashes originales, snapshot, observaciones, promociones y airflow_run_id dan linaje.
- Se reevalúa el champion sin fit/recalibración, con la misma matriz causal y casos
  del candidato. Sus cortes originales deben preceder a la nueva validación. La
  referencia se audita aparte, sin cambiar el run histórico. Si cambia alias entre
  reevaluación y decisión, si las codificaciones difieren o falla la reevaluación,
  se conserva vigente y se informa fallo. Se reutiliza política 1%/5%/10% existente.
- Un fallo de entrenamiento impide ejecutar promoción; no mejora es una ejecución
  exitosa con promovido False. Fallos de publicación/alias usan las compensaciones
  existentes. Mantener un único escritor de promociones (no ejecutar manual y DAG
  simultáneamente). Un timeout de red que impida confirmar rollback se informa.
- Compose migra de esqueleto 2.10 a 3.3.2: api-server + scheduler + dag-processor,
  JWT compartido, SimpleAuth y volúmenes de auth/trabajo. Imagen base fija y virtualenv
  ML separado. Git ausente en imágenes queda explícitamente desconocido en linaje,
  nunca se inventa un commit; opcional NOVAMERCADO_GIT_COMMIT aporta identificación.
- Verificado SDK 3.3.2 real: parseo, serialización y dag.test con PostgreSQL real y
  MLflow aislado. Casos de ejecución correcta, empate de costo y fallo de entrenamiento
  conservan lo esperado. No se construyó ni levantó el stack Airflow de Compose;
  validación de configuración pasó. No se implementaron endpoints administrativos.


## Fase 5 — Endpoints administrativos

- POST sin cuerpo devuelve 202 solo tras confirmar el ID; errores de Airflow son 503.
  Se autentica vía JWT REST v2, activa el DAG pausado y no repite el trigger ante
  timeout: consulta el mismo ID para evitar duplicados. GET distingue desconocido
  (404), en curso y resultados terminales (200), e indisponibilidad (503).
- Finalizador all_done guarda resultado y versión al terminar en XCom. Ante fallo
  previo vuelve a fallar para no convertir el DagRun en exitoso. Si no se conoce
  la versión no inventa una: GET devuelve 503. Sigue vigente la restricción de un
  único escritor de promociones. Consultar no modifica MLflow ni el champion.
- MockTransport cubre contrato, errores y timeout; fixture bloquea Airflow real.
  SDK verifica parseo/serialización y finalizador simulado. Regresión: 233 passed,
  2 deselected (pruebas de entrenamiento real excluidas por instrucción).
  Comprobación posterior focalizada: 36 passed. No se dispararon DAGs.


## Fase 5 — Modelo, salud y actualización sin reinicio

- `/modelo` informa el snapshot cargado (nombre, alias y versión de texto); sin
  snapshot devuelve 503. Se inicia la carga en lifespan sin bloquear el servidor.
  Se recupera automáticamente aunque la carga inicial falle, sin exigir predicción.
- Refresco máximo 30 s, intercambio atómico tras validación y conservación ante
  fallo. La lectura del snapshot no espera una descarga en curso. Una versión
  incompatible no aparece como servida y mantiene la salud degradada.
- `/health`: 503 sin modelo; 200 degradado con motivo si falla DB/MLflow/Airflow
  o el refresco; 200 ok solo con modelo y todas las dependencias disponibles.
  Sondas paralelas, sin caché, HTTP 3 s, conexión PostgreSQL 5 s y sentencia 3 s.
  Airflow verifica los componentes internos, incluso con respuesta HTTP 200.
- Pruebas HTTP con fuente simulada, sin cambiar Registry ni disparar DAGs; cambio
  de versión con intervalo real de 30 s y pruebas de caída/recuperación aceleradas.
  La certificación de tiempos del stack completo y bootstrap permanece pendiente.


## Fase 6 — Inicializador del producto

- Servicio one-shot `product-init`, misma imagen y entorno que API; depende de
  PostgreSQL producto y MLflow, y API espera su éxito y scheduler saludable.
  Imagen local con etiqueta fija y healthcheck API que exige estado ok.
- Migración idempotente también en volumen existente; datos publicados montados
  de solo lectura. Se validan/cargan para entrenar sin generar observaciones
  operativas artificiales. No se duplica el histórico en otra tabla.
- Champion READY existente se conserva; solo RESOURCE_DOES_NOT_EXIST significa
  ausencia. Timeout, permisos y modelo inválido abortan, sin entrenamiento de reemplazo.
- Arranque vacío reutiliza HGB y política existentes; últimas 56 fechas para
  validación, ajuste/calibración causales. Checkpoint durable permite reintentar
  promoción sin fit repetido; cambio de insumos incompleto requiere revisión.
  El bloqueo fcntl protege inicializadores que comparten model-cache; se conserva
  la restricción de un único escritor global. Un crash antes del checkpoint puede
  dejar una versión huérfana: conservarla y revisar, nunca borrar automáticamente.
- Se añade --solo-reutilizar para verificar el stack sin permitir entrenamientos.
  Primer modelo simulado en pytest; el entrenamiento inicial real y readiness
  desde volúmenes vacíos en <=10 min siguen pendientes.
