# Decisiones técnicas y de producto

Contrato funcional y criterios de aceptación: `REQUISITOS.md`. Las pruebas y evidencias trazables se enlazan desde su matriz.

## Datos y calidad de entrada

Los CSV publicados se montan desde `data/` en solo lectura. No se copian a las imágenes ni se versionan. `DATA_DIR` permite usar otra carpeta. Se validan cabeceras, claves, tipos, referencias, duplicados, fechas de apertura, costos y calendario antes de entrenar; datos inválidos abortan en vez de ocultar errores.

La normalización está fuera de los endpoints. Reglas actuales:

| Problema | Acción | Decisión |
|---|---|---|
| ID de tienda numérico como texto o prefijo `T` | Reparar y registrar en calidad | Formato inequívoco; tienda debe existir en catálogo. |
| Familia con mayúsculas, acento, espacios o nombre exacto catalogado | Reparar y registrar | Normalización Unicode/case; sin similitud aproximada que pueda mapear mal. |
| Número entero como texto o decimal integral no ambiguo | Reparar y registrar | Conversión segura; rechazar booleanos, negativos, fracciones, no finitos y separadores ambiguos. |
| Fecha ISO, `DD/MM/AAAA` o ISO a medianoche | Canonizar e informar | No consultar reloj real. Fechas imposibles y horarios distintos se rechazan. |
| Solicitud de pronóstico con subconjunto de familias | Advertir y procesar las recibidas | No inventar familias/promociones. |
| Claves extra/faltantes, null, lista vacía, desconocidos, valores duplicados contradictorios | Rechazar HTTP 422 | No elegir silenciosamente entre valores en conflicto. Duplicado idéntico puede deduplicarse e informarse. |
| Alias `tienda` conocido | Reparar a `tienda_id` | Rechazar si ambos campos aparecen. |
| Venta real negativa | Rechazar | No convertir devoluciones a cero sin una política del negocio. |

Toda reparación/advertencia informa campo, acción y motivo. `advertencia` prevalece sobre `corregido` cuando coexisten. Entrada original y forma canónica se persisten por separado. Las solicitudes rechazadas antes de normalizar no se guardan.

## Variables de configuración

Los valores de ejemplo y nombres exactos están en `.env.example`; los marcadores deben sustituirse en `.env`, que no se versiona. Compose usa estos valores y nombres de servicio:

| Variable | Uso |
|---|---|
| `DATA_DIR` | Directorio de CSV y catálogo de datos montado en solo lectura. |
| `PRODUCT_DB`, `PRODUCT_DB_USER`, `PRODUCT_DB_PASSWORD` | Base y credenciales del PostgreSQL del producto. |
| `AIRFLOW_DB`, `AIRFLOW_DB_USER`, `AIRFLOW_DB_PASSWORD` | Base y credenciales independientes del metastore Airflow. |
| `AIRFLOW_ADMIN_USER`, `AIRFLOW_ADMIN_PASSWORD` | Autenticación de Airflow y llamada administrativa desde API. |
| `AIRFLOW_FERNET_KEY`, `AIRFLOW_SECRET_KEY`, `AIRFLOW_UID` | Cifrado, firma de sesión y UID del contenedor Airflow. |
| `API_PORT`, `MLFLOW_PORT`, `AIRFLOW_PORT` | Puertos publicados en el host. |
| `AIRFLOW_BASE_URL`, `MLFLOW_TRACKING_URI` | URLs desde host; Compose sustituye por direcciones internas donde corresponde. |
| `MODEL_NAME`, `MODEL_CACHE_DIR`, `MODEL_REFRESH_SECONDS` | Modelo registrado, caché local y periodo máximo de consulta del alias. |
| `MLFLOW_HTTP_REQUEST_TIMEOUT`, `MLFLOW_HTTP_REQUEST_MAX_RETRIES` | Tiempo límite y reintentos de solicitudes HTTP a MLflow. |

## Alternativas consideradas y decisión final

Estas son decisiones de implementación actuales, posteriores al análisis de datos. Las hipótesis anteriores a inspeccionar los CSV están en el plan, marcadas como históricas.

| Tema | Alternativa considerada | Decisión final y motivo |
|---|---|---|
| Regla de limpieza | Reparar por similitud difusa nombres no catalogados | Solo canonicalizar alias inequívocos; la similitud puede asignar ventas a otra familia. Rechazar desconocidos con 422. |
| Sustitución de faltantes | Imputar familias o promociones ausentes | No imputar: advertir cuando la solicitud de predicción es parcial y pronosticar únicamente lo enviado. |
| Baseline | Media general reciente | Media estacional por día de semana en los 56 días previos; fallback de la serie reciente, para ofrecer una referencia temporal simple. |
| Modelo | CatBoost o modelos separados por tienda/familia | HistGradientBoosting global. Se integra con dependencias disponibles y comparte señal entre series; la evaluación común mostró menor costo que el baseline. No se mantienen modelos independientes por serie. |
| Cantidad sugerida | Redondear la media esperada o aplicar stock fijo | Cuantil de residuos de calibración según la razón de costos por familia; refleja asimetría de faltantes/sobrantes sin inventar un stock universal. |
| Validación | División aleatoria o ajuste iterativo sobre validación | Cortes cronológicos y calibración anterior al periodo de validación; reduce fuga de futuro. |
| Promoción | Promover por una única métrica técnica | Comparar costo sobre mismos casos y exigir mejora mínima de 1%, límites de regresión de MAE/RMSE/WAPE y de costo por familia. Ante empate, error o regresión, conservar el champion. |
| Disponibilidad ante caída | Consultar MLflow en cada predicción | Mantener un snapshot validado en memoria y refrescar el alias periódicamente; permite servir mientras MLflow está caído. |
| Persistencia de pruebas | Reutilizar el PostgreSQL del producto | Usar PostgreSQL de pruebas exclusivo cuando se habilita integración; no tocar producto ni metastore Airflow. |

## Persistencia y contrato HTTP

`product-db` y `airflow-db` son PostgreSQL separados. El esquema `novamercado` guarda solicitudes, acciones de calidad, predicciones con versión, observación vigente e historial. Una respuesta de predicción 200 requiere que las filas se hayan confirmado. Observaciones usan `(tienda_id, fecha, familia_id)` como clave: nuevo o cambio cuenta 1, idéntico cuenta 0; solicitud, acción e historial forman una transacción.

Rutas del contrato: `POST /v1/prediccion` y `/v1/observaciones`; administración `POST /admin/reentrenar` (sin cuerpo, 202 con ID o 503) y `GET /admin/reentrenar/{id}` (200, 404 desconocido, 503 si no es verificable); `GET /modelo` (nombre/alias/version textuales); `GET /health` (200 ok/degradado con motivo, 503 sin modelo). FastAPI publica `/docs`, `/redoc` y `/openapi.json`.

## Pronóstico y sugerido

Baseline de referencia: media de ventas del mismo día semanal dentro de los 56 días anteriores a D; si no hay muestra semanal, usa historial reciente de esa serie. El sugerido baseline es el cuantil empírico de costo. HGB global usa variables de calendario, tienda, familia, promoción conocida, feriados locales/nacionales, rezagos y estadísticas de ventas anteriores a D. El split es temporal: ajuste, calibración y validación en orden; no hay early stopping aleatorio ni ajuste usando validación.

La cantidad sugerida incorpora el cuantil de residuos de calibración correspondiente a `costo_faltante / (costo_faltante + costo_sobrante)` por familia; queda entero no negativo. Así, un faltante caro eleva el sugerido y un sobrante caro lo reduce. Esto optimiza el costo empírico de calibración bajo estabilidad aproximada de errores; no garantiza costo mínimo futuro ante drift.

La comparación documentada usa 6.720 casos en 2026-01-04–2026-02-28: baseline MAE 53,6474, RMSE 95,5896, WAPE 26,1719%, costo 239.897,90; HGB MAE 38,5310, RMSE 69,6758, WAPE 18,7973%, costo 197.537,70. Ver `evidencias/comparacion_histgradient.json`; no extrapolar automáticamente a otro periodo.

## MLflow y promoción

Tracking/Registry usa servicio `mlflow`, MLflow 3.17.2 y experimento `NovaMercado`. Modelo `novamercado-histgradientboosting`, alias `champion`. Runs contienen parámetros, métricas, artefactos, inputs y linaje SHA256.

Un candidato solo se promueve si READY, run FINISHED, evaluación temporal comparable e insumos/casos iguales; costo total debe bajar al menos 1%, MAE/RMSE/WAPE no pueden empeorar más de 5% y ningún costo por familia más de 10%. Empate, error o regresión conserva el champion. Cada decisión guarda `comparacion_modelos.csv` y `decision_champion.md`. MLflow no ofrece transacción/CAS distribuida para cambiar el alias; mantener un único escritor.

Las pruebas nunca deben seleccionar el tracking por variables heredadas: `tests/conftest.py` fuerza SQLite/servidor local temporal y bloquea clientes externos. Inventario principal comprobado: 14 runs, versiones 1 y 2 READY, champion 1; evidencia de la lectura y comparación está en `evidencias/auditoria_p1.json` y de resiliencia en `evidencias/fase7_resiliencia.json`.

## Airflow, bootstrap y operación

Airflow 3.3.2, DAG manual `novamercado_reentrenamiento`, una ejecución activa, sin schedule/catchup/reintentos y límite global de 10 min. Lee PostgreSQL del producto y combina observaciones vigentes con CSV; para promoción reevalúa champion en el mismo corte. Ante error/no mejora conserva versión actual. El finalizador registra versión vigente en XCom.

En arranque, `product-init` migra idempotentemente y consulta Registry. Reutiliza champion READY; solo si Registry confirma ausencia, valida los CSV, entrena, registra y aplica la política. Error de red/permisos nunca significa Registry vacío. El checkpoint permite reintentar promoción. Un cambio de insumos durante bootstrap interrumpido requiere intervención. No hay bootstrap offline desde caché si MLflow está caído.

FastAPI carga snapshot al iniciar, refresca el alias cada 30 s como máximo e intercambia tras validar; conserva el modelo ante caída de MLflow. `/health` comprueba DB producto, MLflow, metadatabase/scheduler/dag-processor Airflow y snapshot. En Compose aislado: health degradado 1,38 s después de detener MLflow, predicciones continuaron; salud ok 29,03 s después de iniciarlo. Promoción real aislada actualizó FastAPI 13,24 s después de terminar DAG sin reinicio.

Los CSV de la demostración de drift son sintéticos; su promoción no es una afirmación de mejora sobre la demanda futura. La matriz de `REQUISITOS.md` enlaza los checks de clon limpio, tag/remoto, simulación extendida y las evidencias de aceptación.

## Evidencias

- `evidencias/fase_3_1_postgresql.md`: transacciones, concurrencia e idempotencia.
- `evidencias/comparacion_histgradient.json`: métricas y hashes de comparación.
- `evidencias/airflow_fase5.json`: pruebas Airflow SDK aislado.
- `evidencias/fase7_integral.json`: bootstrap y ejecución DAG en Compose aislado.
- `evidencias/fase7_resiliencia.json`, `fase7_promocion_comparacion.csv`, `fase7_promocion_decision.md`: promoción, actualización y caída/retorno.
- `evidencias/auditoria_p1.json`: P1 de contrato, persistencia, costos, Registry y conservación del champion.
- `evidencias/respuestas_api.json`: cuerpos HTTP válidos y 422, con fuente y límites de cada captura identificados.
