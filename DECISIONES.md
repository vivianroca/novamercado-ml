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
