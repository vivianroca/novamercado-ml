# Plan de implementación y matriz de cumplimiento — Laboratorio 2

**Proyecto:** Servicio de ML en Producción — Pronóstico Diario de Ventas para NovaMercado  
**Curso:** Product Development, Maestría en Data Science, cuarto ciclo (octubre de 2026)  
**Documento fuente:** `Laboratorio_2_PD_26_c(1).pdf` (7 páginas)  
**Estado:** Planificación. **Aún no se han descargado los archivos de datos publicados en GES.**  
**Herramienta de desarrollo:** Codex.  
**Propósito de este archivo:** respaldar las decisiones y requisitos antes de implementar, para poder reanudar el proyecto en futuras sesiones y auditar el resultado.  

> **Regla de trazabilidad:** cada obligación se vincula a una página del PDF y deberá tener una prueba o evidencia antes de declarar terminada la implementación. La descripción de un archivo o mecanismo de implementación en este plan **no sustituye** la prueba de que funciona.

## 1. Alcance y criterios de diseño

Construir un producto ejecutable con FastAPI, PostgreSQL, MLflow, Airflow y Docker Compose que:

1. Reciba pronósticos diarios de unidades vendidas por tienda, fecha y familia, devolviendo `venta_esperada` y `cantidad_sugerida`.
2. Tolere entradas defectuosas con políticas justificadas de **reparar, advertir o rechazar**, sin inventar silenciosamente datos.
3. Persista las solicitudes, predicciones, correcciones y ventas reales observadas; mantenga la versión usada para cada predicción.
4. Entrene un modelo inicial de manera autónoma, reentrene con datos nuevos y promueva nuevos modelos solo cuando satisfagan un criterio verificable.
5. Permanezca operativo ante interrupciones temporales de MLflow, preserve estado entre reinicios y pueda ejecutarse con el procedimiento documentado.

**Prioridad:** primero contrato, calidad, persistencia y operación robusta; después mejorar el pronóstico sin comprometer límites de tiempo.

### Clasificación de requisitos

- **[PDF] Obligatorio:** indicado expresamente por el laboratorio.
- **[IMPLEMENTACIÓN] Necesario según nuestra arquitectura:** elección técnica para cumplir lo anterior, no un nombre de archivo exigido por el docente.
- **[OPCIONAL] Mejora:** solo si aporta valor y no compromete plazos.

## 2. Insumos pendientes del GES

El PDF (p. 2) señala que el equipo docente publicará los siguientes archivos. **Ninguno se ha recibido todavía en este proyecto**:

| Insumo | Uso previsto | Estado |
|---|---|---|
| `tiendas.csv` | Catálogo de tiendas, formatos y ciudades | Pendiente de descargar |
| `familias.csv` | Catálogo de familias y normalización de IDs | Pendiente de descargar |
| `historico_ventas.csv` | Dos años de ventas diarias y `en_promocion` por tienda/familia | Pendiente de descargar |
| `feriados.csv` | Feriados nacionales/locales, fechas comerciales y de pago, incluidos días futuros | Pendiente de descargar |
| `costos.csv` | Costos relativos de faltantes/sobrantes por familia | Pendiente de descargar |
| `catalogo_errores.md` | Ejemplos y tipos de problemas observados; no exhaustivo | Pendiente de descargar |
| `ejemplos/` | Solicitudes válidas y defectuosas | Pendiente de descargar |

**Reglas de integración de insumos [PDF, p. 2]:**
- En `feriados.csv`, `ambito` vale `nacional` o el nombre de ciudad que coincide con `ciudad` en `tiendas.csv`.
- El sistema recibe observaciones de ventas del día anterior **antes** del pronóstico del día siguiente.
- Las observaciones **no** contienen promociones; `en_promocion` del día de pronóstico llega en la solicitud.
- No usar el reloj real para invalidar fechas: el servicio opera con **fechas simuladas**; la evaluación es posterior al histórico y está cubierta por el calendario de feriados.
- El docente colocará los insumos en la carpeta señalada en el README al evaluar. El primer arranque debe funcionar a partir de esos archivos.

**Pendiente antes de codificar reglas concretas de calidad y modelo:** inspeccionar cabeceras, tipos, rangos, nulos, duplicados, claves y ejemplos reales. No inventar columnas ni contenido de los CSV.

## 3. Matriz de requisitos y pruebas de aceptación

**Estado inicial de todos los criterios:** PENDIENTE. Registrar en esta tabla el archivo, prueba y evidencia real a medida que se implemente.

| ID | Requisito [PDF] | Página | Prueba o evidencia exigida para cerrar | Estado |
|---|---|---|---|---|
| R01 | Pronóstico por tienda, familia y fecha, con venta esperada y sugerido | 1, 6 | Serving champion real versión 1, dos familias y persistencia; `evidencias/prediccion_champion.json` y pruebas aisladas | Verificado |
| R02 | Políticas coherentes para reparar, advertir o rechazar defectos, también no catalogados | 1–2 | Pruebas parametrizadas con ejemplos y nuevos casos | Pendiente |
| R03 | Las respuestas explican correcciones/advertencias | 2, 6 | Verificar `calidad.estado` y observaciones | Pendiente |
| R04 | Contrato exacto de API con Pydantic y limpieza fuera de endpoints | 2, 6–7 | Pruebas de esquema, estructura de código y 422 | Pendiente |
| R05 | pytest del contrato independientes de un MLflow activo | 2 | Ejecutar suite con MLflow apagado/mockeado | Pendiente |
| R06 | PostgreSQL de producto distinto al de Airflow, en Docker | 3 | Comprobar separación y conexiones con Compose | Pendiente |
| R07 | Persistir solicitudes, predicciones, correcciones, observaciones y versión por predicción | 1, 3 | Consultar DB tras solicitudes y reinicio | Pendiente |
| R08 | Observaciones idempotentes | 3, 7 | `tests/test_persistencia.py`: HTTP 200, reenvío 0, nuevos + modificados, concurrencia sin duplicados; evidencia en `evidencias/fase_3_1_postgresql.md` | Verificado |
| R09 | Baseline y al menos un modelo ML que mejore al baseline | 3 | `evidencias/comparacion_histgradient.json`: mismo periodo/casos, HGB mejora MAE/RMSE/WAPE/costo; `tests/test_histgradient.py` | Verificado offline |
| R10 | Métricas técnicas y costos de negocio basados en `costos.csv` | 2–3 | Comparativa calculada con fórmula del PDF | Pendiente |
| R11 | Cantidad sugerida coherente con costo por familia | 2–3 | Casos con distintas relaciones de costos y explicación | Pendiente |
| R12 | Experimentos, modelos, linaje y alias vigente en MLflow Registry | 3 | Capturas/consultas de runs, artefactos, versiones y alias | Pendiente |
| R13 | Criterio automatizado y explícito de promoción | 3 | `ml/promocion.py`, `tests/test_promocion.py`, `tests/test_promocion_mlflow.py`: mejora, empate, retroceso y error; decisiones auditadas | Verificado |
| R14 | Airflow reentrena usando histórico y observaciones persistidas | 3 | DAG SDK 3.3.2 ejecutado con histórico y 66 observaciones PostgreSQL, MLflow aislado; `evidencias/airflow_fase5.json` | Verificado con SDK; stack pendiente |
| R15 | Reentrenamiento invocable por API y estado consultable | 3, 7 | POST 202/503, GET estados y GET 404 | Verificado con Airflow simulado |
| R16 | Modelo promovido se usa en API sin reinicio ≤2 min tras el DAG | 3 | Cambio de fuente simulado y HTTP con intervalo real de 30 s; sin ejecutar DAG | Verificado en API aislada; stack pendiente |
| R17 | Fallo o candidato descartado no afecta modelo vigente | 3 | Simular fallo y no promoción; continuidad de predicciones | Pendiente |
| R18 | Todo se levanta con `docker compose up` y servicio llamado `mlflow` | 3 | `docker compose config`, `up`, `ps`, curl | Pendiente |
| R19 | Primer arranque: carga datos y entrena/registra modelo automáticamente | 3 | product-init y tests/test_bootstrap.py | Implementado y simulado; entrenamiento inicial real pendiente |
| R20 | Arranque posterior: conservar estado, no repetir bootstrap | 3 | Reinicio real API/DB/MLflow; 14 runs y champion 1; checkpoint y concurrencia probados | Verificado con champion existente |
| R21 | Versiones fijas de imágenes; ni credenciales ni datos en imagen/repositorio; `.env.example` | 3 | Revisar Compose, Dockerfiles y `git ls-files` | Pendiente |
| R22 | API sigue prediciendo con modelo cargado si MLflow cae | 3 | Interrumpir MLflow; POST predicción debe funcionar | Pendiente |
| R23 | `/health` degradado en <1 min de caída, ok en <2 min de retorno | 3 | Sondas inmediatas y caída/recuperación simuladas en tests/test_estado.py | Verificado con dependencias simuladas |
| R24 | Salud `ok` ≤10 min del arranque (sin contar build) | 4 | Arranque limpio cronometrado | Pendiente |
| R25 | Reentrenamiento finaliza ≤10 min | 4 | DAG real cronometrado | Pendiente |
| R26 | README desde cero y ubicación de insumos | 4 | Ejecutar literalmente las instrucciones en entorno limpio | Pendiente |
| R27 | Archivo de contexto para agente (`AGENTS.md`, `CLAUDE.md` o similar) | 4 | Archivo incluido y vigente | Pendiente |
| R28 | `DECISIONES.md` documenta políticas, variables, sugerido, promoción, alternativas | 4 | Auditoría documental contra decisiones implementadas | Pendiente |
| R29 | Repo GitHub accesible y tag exacto `entrega-lab2` anterior al límite | 4–5 | Verificar remoto, `git show entrega-lab2` y fecha | Pendiente |
| R30 | Evidencias MLflow, DAG y respuestas válidas/defectuosas | 5 | Evidencias incorporadas al repositorio | Pendiente |
| R31 | Evaluación simula errores inéditos, drift, caídas y reinicios | 4 | Simulación integrada de varios días y fallos | Pendiente |

### 3.1 Contrato externo: implementar **exactamente** el anexo [PDF, pp. 6–7]

**Puerto**: `8000`. **Fechas**: `AAAA-MM-DD`. **Rechazos**: HTTP `422` con `detail` explicativo.

**POST `/v1/prediccion`**

Solicitud ejemplificada:
```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "familias": [
    {"familia_id": "abarrotes", "en_promocion": 0},
    {"familia_id": "bebidas", "en_promocion": 8}
  ]
}
```

Respuesta 200 debe incluir:
- `tienda_id`, `fecha`, `version_modelo` (texto).
- `predicciones[]` con `familia_id`, `venta_esperada` y `cantidad_sugerida` (entero no negativo).
- `calidad` con `estado` y `observaciones`.
- `calidad.estado` solo puede ser `ok` (sin problemas; observaciones vacías), `corregido` (reparaciones) o `advertencia` (si hubo **alguna** advertencia, aunque también se hayan reparado campos).
- Cada observación de calidad contiene `campo`, `accion` (`reparar`/`advertir`) y `detalle`.
- Puede haber **varias solicitudes de pronóstico para la misma tienda/fecha**.

**POST `/v1/observaciones`**

Solicitud ejemplificada:
```json
{
  "tienda_id": 5,
  "fecha": "2025-11-17",
  "ventas": [
    {"familia_id": "abarrotes", "ventas": 994}
  ]
}
```

Respuesta 200 incluye `registros_guardados` y `calidad`; `registros_guardados` cuenta los registros **nuevos o modificados** en esa solicitud. Reenviar una observación **idéntica** debe devolver 0.

**POST `/admin/reentrenar`**
- Sin cuerpo. HTTP `202`, JSON con `id` de ejecución como texto.
- HTTP `503` si no se puede iniciar.

**GET `/admin/reentrenar/{id}`**
- `estado`: `en_curso`, `exitoso`, `fallido`.
- Cuando termina: `promovido`, `version` y `motivo`; `version` corresponde al **modelo vigente al terminar**, no necesariamente al candidato.
- ID desconocido: HTTP `404`.

**GET `/modelo`**
- `nombre`, `alias`, `version`: todos **texto**; deben describir el modelo efectivamente utilizado por la API.

**GET `/health`**
- HTTP `200`, `estado: ok` solo si funcionan API, DB, MLflow, Airflow y hay modelo cargado.
- HTTP `200`, `estado: degradado` + `motivo` cuando responde pero falla una dependencia.
- HTTP `503` cuando **no hay modelo cargado**.

**Nota de pruebas:** pueden existir campos adicionales en respuestas, pero no se pueden omitir ni renombrar los del anexo.

### 3.2 Fórmula y restricciones temporales

[PDF, pp. 2–3] Costo por tienda, familia y día:

```text
costo = c_faltante * max(real - sugerido, 0)
      + c_sobrante * max(sugerido - real, 0)
```

- Las ventas se expresan **en unidades**.
- Al emitir un pronóstico de día D, solo se conocen observaciones de **días anteriores**.
- La promoción del día D viene de la solicitud de pronóstico y no de observaciones.
- Los feriados locales se aplican según ciudad; validar datos de feriados futuros sin extrapolar indebidamente.
- Validaciones temporales de entrenamiento y selección deben impedir fuga de información.

## 4. Decisiones preliminares de arquitectura (no confundirse con requisitos literales)

| Tema | Propuesta | Clasificación | Confirmar con datos |
|---|---|---|---|
| Orquestación local | `compose.yaml` con API, DB producto, MLflow y Airflow y sus dependencias | IMPLEMENTACIÓN (Compose sí obligatorio; nombre `.yaml` no) | No |
| Entrenamiento inicial | Servicio/tarea de bootstrap idempotente, coordinado por Compose | IMPLEMENTACIÓN | Sí, rendimiento |
| PostgreSQL | DB producto independiente de DB/metastore de Airflow | PDF | No |
| Configuración | `.env.example` sin secretos; variables desde `.env` local ignorado | PDF + IMPLEMENTACIÓN | No |
| FastAPI | Routers, esquemas Pydantic, servicios de limpieza separados | PDF + IMPLEMENTACIÓN | Sí, errores reales |
| Pronóstico | Baseline simple estacional + un modelo ML global con rasgos de tienda/familia, calendario y promociones | IMPLEMENTACIÓN; baseline y ML sí PDF | Sí |
| Algoritmo | Probar HistGradientBoosting o CatBoost, sin decidir antes del EDA | IMPLEMENTACIÓN | Sí |
| Cantidad sugerida | Estimar un cuantil de demanda basado en costos si existe distribución/estimación fiable; si no, calibración validada por costo | IMPLEMENTACIÓN; coherencia de costos sí PDF | Sí |
| Registro | Persistir versión por cada predicción, valores de entrada corregidos y advertencias; mantener observaciones idempotentes | PDF + IMPLEMENTACIÓN | No |
| Modelo activo | Alias estable en MLflow Registry y caché local/artefacto cargado en memoria | PDF + IMPLEMENTACIÓN | No |
| Refresco automático | Verificar alias/versión periódicamente, con frecuencia que garantice <2 min | IMPLEMENTACIÓN | No |
| Sin MLflow | Predicciones con modelo ya cargado; salud degradada y recuperación comprobables | PDF | No |
| Promoción | Elegir candidato solo si reduce costo validado frente al vigente y supera controles de calidad y estabilidad | IMPLEMENTACIÓN; criterio explícito automatizado sí PDF | Sí |
| Reentrenamiento | DAG disparado mediante endpoint administrativo; observa datos persistidos y no bloquea API | PDF + IMPLEMENTACIÓN | No |
| Git | Commits al terminar cada fase; tag `entrega-lab2` solo tras auditoría | IMPLEMENTACIÓN + PDF | No |

**Cuidados técnicos:**
- El servicio `mlflow` debe llamarse exactamente así en Compose.
- **No** descargar un modelo de MLflow en cada predicción; conservar modelo cargado y disponer de estrategia de actualización y recuperación.
- Persistir los artefactos del modelo y la metadata de MLflow para sobrevivir reinicios; validar que API y Registry no diverjan.
- Los datos y secretos reales no deben entrar en Git ni en imágenes. Usar `.gitignore`, `.dockerignore` y montajes de volumen/configuración externa.
- Evitar complejidad innecesaria (varios modelos por cada tienda/familia) antes de medir el beneficio.
- La propuesta de cuantil `c_faltante / (c_faltante+c_sobrante)` es una **decisión de modelado condicionada a una distribución predictiva adecuada**, no una exigencia textual ni garantía automática de mejora.

## 5. Archivos propuestos y distinción entre lo requerido y lo opcional

| Ruta propuesta | Propósito | Naturaleza |
|---|---|---|
| `README.md` | Levantar desde cero, ruta de insumos, ejecución, pruebas y evidencias | PDF, nombre explícito |
| `DECISIONES.md` | Políticas, alternativas, justificaciones del modelo, sugerido y promoción | PDF, nombre explícito |
| `AGENTS.md` | Contexto, objetivos, instrucciones para Codex | PDF exige archivo equivalente; nombre elegido |
| `.env.example` | Variables necesarias sin secretos | PDF, nombre explícito |
| `compose.yaml` | Describir servicios y dependencias de Docker Compose | IMPLEMENTACIÓN para cumplir Compose; **no** exigir archivos YAML arbitrarios |
| `Dockerfile`, `airflow/Dockerfile` | Construcción de imágenes propias | IMPLEMENTACIÓN si se requieren |
| `requirements.txt` (u otro lock/gestor) | Dependencias reproducibles | IMPLEMENTACIÓN |
| `.gitignore`, `.dockerignore` | Excluir secretos, datos y artefactos no permitidos | IMPLEMENTACIÓN |
| `app/` | Endpoints, esquemas, lógica de calidad, servicios, DB | PDF exige código, organización propuesta |
| `ml/` | Entrenamiento, features, predicción, evaluación, Registry | PDF exige modelos, organización propuesta |
| `airflow/dags/reentrenamiento.py` | DAG de reentrenamiento | PDF exige DAG, ruta y nombre propuestos |
| `tests/` | pytest del contrato, calidad, DB, operación | PDF exige pruebas, rutas propuestas |
| `data/` | **Carpeta vacía/documentada** para archivos del GES | IMPLEMENTACIÓN; contenidos pendientes |
| `evidencias/` | Capturas/logs/ejemplos validados | PDF exige evidencia, ruta propuesta |
| `config/modelo.yaml`, `config/calidad.yaml` | Configuración opcional del modelo/reglas | OPCIONAL; **NO exigidos por PDF** |
| `Makefile`, `pytest.ini` | Comodidades de desarrollo | OPCIONAL |

### Estructura preliminar

```text
novamercado/
├── AGENTS.md
├── README.md
├── DECISIONES.md
├── .env.example
├── .gitignore
├── .dockerignore
├── compose.yaml
├── Dockerfile
├── requirements.txt
├── app/
│   ├── main.py
│   ├── api/
│   ├── schemas/
│   ├── calidad/
│   ├── servicios/
│   └── db/
├── ml/
│   ├── entrenamiento.py
│   ├── prediccion.py
│   ├── evaluacion.py
│   └── registry.py
├── airflow/
│   ├── Dockerfile
│   └── dags/
│       └── reentrenamiento.py
├── data/                     # Insumos del GES: no subir datos al repo
├── tests/
└── evidencias/
```

**La estructura es provisional:** tras inspeccionar insumos y versiones elegidas, se puede ajustar sin alterar obligaciones externas.

## 6. Fases de trabajo con Codex y puertas de salida

**Modo de trabajo:** una fase por prompt, cambios acotados, ejecutar pruebas, revisar diferencias, realizar commit, actualizar la matriz. Codex no debe completar fases futuras ni modificar requisitos del anexo sin justificarlo.

### Fase 0 — Auditoría previa (sin implementar lógica)
- Leer PDF, este plan y los archivos cuando estén disponibles.
- Crear/actualizar matriz de cumplimiento y lista de casos de prueba, identificando dependencias.
- Distinguir explícitamente obligaciones y opciones; identificar contradicciones o datos faltantes.
- **Salida:** matriz revisada y plan de pruebas; ninguna suposición sobre contenido de CSV no recibidos.

### Fase 1 — Esqueleto, entorno y Compose mínimo
- Crear repositorio y `AGENTS.md`, `README.md` inicial, `.env.example`, ignore files, estructura modular.
- Crear `compose.yaml` con servicio `mlflow` y diseños claros de DB producto y metastore Airflow.
- Fijar versiones de imágenes y librerías de forma reproducible; parametrizar credenciales.
- **Salida:** `docker compose config --quiet` sin errores; estructura auditable; ninguna contraseña ni archivo GES versionado.

### Fase 2 — Contrato FastAPI y política de calidad
- Implementar los endpoints del anexo y esquemas Pydantic; normalización/limpieza en módulos independientes.
- Documentar reglas reparar/advertir/rechazar por tipo de problema, de modo extensible.
- Montar tests unitarios de API con dependencias simuladas (sin MLflow).
- **Salida:** pytest independiente de MLflow y respuestas estructuralmente idénticas al anexo (funcionalidad de ML inicialmente simulada).

### Fase 3 — Persistencia e idempotencia
- Implementar tablas/consultas y migraciones o inicialización controlada en PostgreSQL producto.
- Guardar entrada original/canónica, acciones de calidad, predicción con versión y ventas observadas.
- Manejar nuevas observaciones, correcciones y duplicados; idempotencia por clave natural.
- **Salida:** tests de persistencia y reenvío idéntico con 0 cambios; datos sobreviven reinicio.

### Fase 4 — Entrenamiento, costo e MLflow
- Con datos GES reales, EDA enfocado en integridad y separación temporal.
- Entrenar baseline y candidato ML; registrar métricas técnicas y costo de negocio.
- Calibrar `cantidad_sugerida` con costos reales y validación temporal; documentar comparación.
- Guardar linaje, artefactos, versiones y alias de modelo vigente en MLflow.
- **Salida:** evidencia reproducible de modelo ML mejor que baseline, y predicciones reales mediante API con versión.

### Fase 5 — Airflow y promoción
- DAG que lee histórico y observaciones persistidas para reentrenar y evaluar.
- Implementar endpoints administrativos y consulta del estado por ID.
- Aplicar regla de promoción; preservar alias vigente ante fallo/no mejora.
- Actualizar modelo servido sin reinicio y en ≤2 minutos tras finalizar DAG.
- **Salida:** ejecución completa, seguimiento por API y pruebas de promoción/no promoción/fallo.

### Fase 6 — Inicialización automática y resiliencia
- Bootstrap automático desde datos GES cuando no hay modelo; no repetir en siguientes arranques.
- Healthchecks de dependencias y recuperación de MLflow.
- Pruebas de caída de MLflow (predicción continúa), health degradado <1 min, ok <2 min tras retorno.
- **Salida:** `docker compose up` desde limpio, `/health` ok ≤10 min sin build; cada reentrenamiento ≤10 min; persistencia post-reinicio.

### Fase 7 — Documentación y evidencias
- Completar README desde cero, `DECISIONES.md`, esquema de datos y guía de uso/diagnóstico.
- Capturar experimentos/Registry de MLflow, ejecuciones DAG y ejemplos de API buenos/defectuosos.
- Ejecutar simulación diaria de observación D−1 → predicción D, fechas futuras, cambios de demanda.
- **Salida:** un tercero puede clonar, colocar insumos y ejecutar sin intervención manual.

### Fase 8 — Auditoría final y entrega
- Revisar **cada** R01–R31 con archivo, prueba y evidencia, cerrando desviaciones.
- Verificar ausencia de secretos/datos en Git, versiones fijas y nombre exacto `mlflow`.
- Probar reinicio sin eliminar volúmenes, caída/retorno de MLflow y actualización sin reinicio.
- Crear tag exacto `entrega-lab2` en el commit final **antes** de la fecha límite informada en GES; comprobar remoto y acceso del docente.
- Entregar **únicamente enlace de GitHub** en GES (según PDF).
- **Salida:** matriz sin requisitos pendientes y entrega reproducible.

## 7. Pruebas críticas del evaluador (simulación de punta a punta)

1. Clonar exactamente el tag `entrega-lab2`.
2. Colocar los archivos publicados en la ruta indicada por `README.md`, sin copiar secretos al repositorio.
3. `docker compose up` en entorno limpio: comprobar que el primer modelo aparece automáticamente y `/health` pasa a `ok` en ≤10 min (sin contar build).
4. Enviar solicitudes de pronóstico correctas, con IDs/fechas/números mal formateados y problemas **no** incluidos en el catálogo; validar reparar/advertir/rechazar, `calidad` y HTTP 422.
5. Solicitar dos veces pronóstico para tienda/fecha: ambos deben funcionar y mantener trazabilidad de solicitudes/versiones.
6. Enviar observación real del día D; reenviarla idéntica: segundo `registros_guardados = 0`.
7. Simular múltiples días: observaciones D−1 antes de pronóstico D; impedir leakage.
8. Solicitar reentrenamiento mediante POST; consultar estado en GET hasta terminal; medir ≤10 min.
9. Forzar escenario de candidato promovido: validar versión servida actualizada en ≤2 min sin reinicio.
10. Forzar escenario de candidato rechazado o entrenamiento fallido: modelo vigente sin alteración.
11. Interrumpir solo MLflow: predicción sigue funcionando; salud degradada <1 min; al restablecerlo salud ok <2 min.
12. Reiniciar sin borrar volúmenes: datos/Registry/modelo conservados, bootstrap no duplicado.
13. Verificar `DECISIONES.md`, `README.md`, pruebas y evidencias de todo lo anterior.

## 8. Política de trabajo y control de cambios

- Codex trabaja en el repositorio de este laboratorio; **no mezclar con el laboratorio anterior** salvo que se decida expresamente.
- Por cada fase: plan pequeño → cambios → tests → revisión → commit → actualizar matriz.
- No afirmar que algo pasó sin ejecutar comandos o mostrar evidencia.
- No cambiar nombres de campos, rutas o códigos del contrato por conveniencia.
- Registrar en `DECISIONES.md` alternativas evaluadas y razones; no inventar resultados experimentales.
- No subir los archivos de datos del GES sin verificar condiciones de uso; el PDF requiere que el evaluador los coloque localmente, no versionarlos.
- Si faltan datos, implementar únicamente componentes que no dependan de observar los archivos reales; **no simular un esquema supuesto como definitivo**.
- Elegir herramientas y modelos con tiempos de arranque/entrenamiento dentro de los límites impuestos.

## 9. Pendientes y riesgos por resolver

| Tema | Acción posterior |
|---|---|
| Archivos GES aún no descargados | Descargar siete insumos e inspeccionarlos antes de definir políticas definitivas o entrenar |
| Catálogo de errores no exhaustivo | Definir reglas generales y pruebas adversariales, no solo copiar ejemplos |
| Datos históricos/observaciones potencialmente superpuestos | Definir reconciliación por clave y no duplicar entrenamiento |
| Métrica de costo y sugeridos | Validar según costos reales por familia, no usar heurística sin comprobar |
| Cambio de patrón de demanda | Evaluación temporal y reentrenamiento con observaciones recientes |
| Latencia de actualización del modelo | Cache y refresco comprobado con reloj/tiempos de prueba |
| Recuperación tras fallo MLflow | Asegurar que un modelo ya cargado sigue disponible; cache/artefactos persistidos |
| Tiempo máximo 10 min | Medición bajo infraestructura real; limitar candidatos y ejecución del DAG |
| Fecha límite | Consultar GES; no consta en el PDF |
| Ambigüedad de reglas puntuales de limpieza | Resolver con inspección de datos y registrar políticas explícitas en `DECISIONES.md` |

## 10. Estado actual y primer paso pendiente

- [x] PDF de 7 páginas revisado y requisitos extraídos.
- [x] Plan y matriz de cumplimiento documentados.
- [ ] Insumos GES descargados.
- [ ] Repositorio inicializado.
- [ ] Fase 0 ejecutada en Codex.
- [ ] Implementación y evidencias.
- [ ] Auditoría final y tag `entrega-lab2`.

**Siguiente acción sugerida:** guardar este archivo en la raíz del repositorio futuro; cuando estén disponibles los insumos, descargarlos y ejecutar la Fase 0 en Codex para ajustar matriz y secuencia según los datos reales. Hasta entonces, este documento es la referencia de planificación, no una declaración de que el laboratorio ya cumple requisitos.

## 11. Actualización de avance — 2026-11-14

Esta actualización sustituye los estados iniciales anteriores sobre disponibilidad
de insumos y repositorio: Git ya está inicializado con remoto `origin`; los cinco
CSV, catálogo y ejemplos están en `data/` (tras moverlos desde `../datos_lab2/`)
y se han inspeccionado. Su contenido está ignorado por Git salvo `.gitkeep`;
Compose y `.env.example` usan `./data` por defecto.
El PDF de siete páginas fue contrastado nuevamente sin discrepancias sustanciales.

Fase 1: estructura modular, contexto, documentación inicial, ignore files,
variables de ejemplo, dependencias directas fijas, Dockerfile y Compose creados.
Servicios: API, PostgreSQL producto, PostgreSQL Airflow, MLflow, inicialización,
webserver y scheduler Airflow. Insumos externos en solo lectura y volúmenes
persistentes declarados.

Evidencia ejecutada: `docker compose --env-file .env.example config --quiet`
terminó con código 0; `config --services` enumeró los siete servicios.
`git check-ignore` confirmó exclusión de `.env`, datos y artefactos locales.
No se construyeron imágenes ni se arrancaron contenedores.

R21 y R26–R28 tienen avances documentales/configuración, pero permanecen pendientes
de validación completa. El resto de R01–R31 sigue pendiente de funcionamiento.
Las dependencias transitivas aún no están bloqueadas. No se implementaron
endpoints del contrato, limpieza, persistencia de negocio, modelos, DAG ni bootstrap.
Siguiente fase: contrato FastAPI y política de calidad (Fase 2).

### Fase 2.1 — Esquemas y normalización

- Implementados `app/schemas/solicitudes.py` y `app/calidad/normalizacion.py`:
  solicitudes canónicas, calidad por campo y rechazo explicativo preparado para 422.
- Políticas E01–E10 y casos generales documentados en `DECISIONES.md`.
- Evidencia: `.venv/bin/python -m pytest -q`, Python 3.12: **49 passed**,
  incluidos los 12 JSON docentes. Sin servidor ni paquete MLflow.
- R02–R05 y R28 avanzan parcialmente; siguen pendientes la integración HTTP,
  las respuestas completas y las pruebas de endpoints. R08 no se declara cerrado:
  la idempotencia persistida pertenece a Fase 3.
- Sin persistencia, modelos, DAG, construcción ni arranque de contenedores.

### Fase 2.2 — Endpoints de predicción y observaciones

- Implementados ambos POST del anexo, reutilizando normalización, con esquemas
  de respuesta, códigos 200/422 y protocolos sustituibles de predicción/registro.
- Sin backend configurado responden 503, sin simular resultados o guardados.
- Evidencia: `.venv/bin/python -m pytest -q`: **91 passed**, una advertencia de
  obsolescencia de Starlette/AnyIO. Incluye contratos HTTP, entradas defectuosas,
  normalización delegada, indisponibilidad y validación de resultados del proveedor.
- R01, R03–R05 avanzan con pruebas HTTP sin MLflow. No se declaran cerrados R01/R07/R08:
  faltan predicción real y persistencia/idempotencia. Endpoints administrativos y
  salud/modelo también siguen pendientes. No se implementaron ML ni persistencia.

### Fase 3.1 — Esquema y capa PostgreSQL del producto

- Implementados esquema SQL, inicializador explícito y repositorio transaccional
  para solicitudes originales/canónicas, acciones de calidad, predicciones con
  versión y observaciones vigentes con historial de cambios.
- Observaciones: UPSERT por tienda/fecha/familia, sin actualizar reenvíos idénticos;
  contador solo después de commit. Predicciones: se registra antes de responder 200.
- `product-db` monta la inicialización SQL exclusivamente en su volumen nuevo.
  No se cambió ni utilizó la base Airflow.
- Evidencia aislada: pytest **94 passed, 6 skipped**, una advertencia externa de
  Starlette/AnyIO. Las seis pruebas omitidas requieren `TEST_PRODUCT_DB_DSN` y
  verifican idempotencia real, concurrencia, historial, rollback, predicciones
  repetidas e integración HTTP contra PostgreSQL.
- No hay PostgreSQL local ni contenedores activos. Se solicitó autorización para
  iniciar un PostgreSQL temporal de pruebas; mientras esté pendiente, R07/R08
  permanecen pendientes de integración real. Tampoco se declara probada la
  persistencia tras reinicio. Sin ML ni reentrenamiento.

### Verificación PostgreSQL de Fase 3.1

Con autorización del usuario se inició únicamente PostgreSQL 16.8 temporal,
con almacenamiento tmpfs, puerto local aleatorio y sin montar volúmenes existentes.
Suite completa: **100 passed, 0 skipped**, una advertencia de Starlette/AnyIO.
Pasaron las seis pruebas de integración, incluidos idempotencia, concurrencia,
rollback y HTTP con nuevos + modificados. R08 verificado; R07 sigue pendiente
de la prueba operativa de reinicio. El contenedor temporal se detuvo al finalizar.
Detalle: `evidencias/fase_3_1_postgresql.md`. No se implementó ML.

### Conexión de endpoints con PostgreSQL real

Se verificó el cableado existente con tres pruebas adicionales sin sustituir
dependencias FastAPI: catálogos por `DATA_DIR`, conexión por `PRODUCT_DB_*` y
repositorio real. Observaciones: HTTP 200 con conteos 1, 0, 2, 0 y consultas de
auditoría. Predicción sin modelo: HTTP 503 sin escrituras. Rechazo 422 y error de
DB 503 tampoco confirman registros. Suite completa contra PostgreSQL temporal:
**103 passed, 0 skipped**, una advertencia de Starlette/AnyIO. Contenedor detenido,
sin modificar volúmenes existentes. Reinicio operativo del producto aún pendiente;
sin ML ni reentrenamiento.

### Fase 4.1 — Baseline temporal y costo

- Implementados `ml/baseline.py`, `ml/datos.py` y `ml/evaluacion.py`: media semanal
  por tienda/familia, ventana fija de 56 días y sugerido por cuantil empírico de costos.
- Validación diaria progresiva: entrenamiento inicial anterior a 2026-01-04;
  validación hasta 2026-02-28. Solo se incorporan observaciones tras pronosticar su día.
- 6 720 casos: MAE 53.6474, RMSE 95.5896, WAPE 26.1719%; costo 239 897.90 frente
  a 292 502.10 usando la media redondeada. La mejora de costo no es uniforme por familia.
- Evidencia reproducible con métricas por familia y hashes: `evidencias/baseline_4_1.json`.
- Pruebas: 22 nuevas; suite completa **125 passed, 0 skipped**, una advertencia
  externa de Starlette/AnyIO. Incluye exclusión de día actual/futuro, aislamiento de
  series, selección de cuantil, métricas con ceros y secuencia temporal.
- R09 parcial: baseline disponible; aún falta un modelo ML que lo mejore.
  R10/R11 avanzan con evaluación del baseline, sin declarar completa la Fase 4.
- Sin MLflow, modelos avanzados ni integración del baseline al endpoint.

### Tracking MLflow del baseline existente

Implementado `ml/tracking.py`: registro sin reentrenar, experimento `NovaMercado`,
cliente 2.22.0 y servicio Compose `mlflow`. Run verificado `a65d9a88bf3d4d1383ac665ff66355a0`
en FINISHED: 9 parámetros, 91 métricas, cuatro datasets con digest, reporte,
configuración, código y manifest de linaje. Reporte y snapshots descargados y
verificados contra originales/hashes. Evidencia: `evidencias/mlflow_baseline.json`.
R12 avanza en tracking/linaje; modelo ejecutable, Registry, alias y promoción
siguen pendientes. No se entrenaron modelos ni se conectó predictor a la API.

Pruebas: **131 passed, 0 skipped**, dos advertencias externas de obsolescencia;
incluye seis nuevas de tracking con cliente sustituido y regresión PostgreSQL real
temporal. Compose validado sin construir imágenes. MLflow queda activo en 5001
con metadata/artefactos persistentes; el PostgreSQL temporal fue detenido.

### Actualización MLflow a 3.17.2

- Imagen Compose y `mlflow-skinny` fijados a 3.17.2. Dependencias instaladas y
  `pip check` sin conflictos; Compose válido.
- Respaldo previo consistente de SQLite y artefactos en `.backups/`, ignorado por
  Git/Docker; inventario de tres runs. Se ejecutó upgrade de DB con 3.17.2 y se
  reutilizaron los mismos volúmenes de metadata y artefactos.
- Verificados todos los runs previos, métricas, parámetros, tags, inputs y hashes
  de artefactos. Baseline original sigue FINISHED y visible en el mismo experimento.
- Registry/aliases probados con metadata temporal aislada, sin modelo de producto,
  entrenamiento ni promoción. También se verificó registro del mismo reporte con
  cliente 3.17.2, UI y host interno `mlflow:5000`.
- Pruebas: **131 de regresión + 4 de compatibilidad aprobadas**, sin omisiones ni
  fallos. PostgreSQL temporal detenido; MLflow 3.17.2 permanece healthy en 5001.
- Evidencia: `evidencias/mlflow_upgrade_3_17_2.json`. Sin funcionalidades nuevas.

### Fase 4 — HistGradientBoosting

- Features causales de calendario, tienda/familia, promociones, feriados nacionales
  y locales, rezagos y agregados. 36 variables; NaN para pasado no observado.
- Ajuste único hasta 2025-12-06, calibración de sugeridos por costos hasta
  2026-01-03, validación idéntica al baseline en 2026-01-04–2026-02-28 (6 720 casos).
  Sin early stopping aleatorio, búsqueda sobre validación ni reentrenamiento.
- HGB: MAE 38.5310, RMSE 69.6758, WAPE 18.7973%, costo 197 537.70. Baseline:
  MAE 53.6474, RMSE 95.5896, WAPE 26.1719%, costo 239 897.90.
- Run MLflow `644650a470024476a8926b64837c5984`, experimento NovaMercado, FINISHED.
  Modelo pyfunc ejecutable `novamercado-histgradientboosting` versión 1, READY;
  cinco datasets con digest, parámetros, comparación, métricas, código y linaje.
  Descarga/carga verificada; sin alias ni promoción.
- Pruebas: **147 passed, 0 skipped**, tres advertencias de dependencias/entorno.
  Incluye 12 nuevas de causalidad, ciudades, calibración temporal, costos,
  serialización y coincidencia de salida; integración PostgreSQL y MLflow también pasó.
- Evidencia: `evidencias/comparacion_histgradient.json`; decisiones y comando en
  DECISIONES/README. API, promoción y reentrenamiento siguen fuera de alcance.

### Política de promoción champion

- Implementada en `ml/promocion.py` e invocada automáticamente tras finalizar el
  entrenamiento. Ahorro mínimo 1%, sin regresión técnica >5% ni costo familiar >10%.
  Validación de READY/FINISHED, temporalidad, métricas, casos e insumos comparables.
- Cada evaluación crea un run propio en NovaMercado con los archivos exactos
  `comparacion_modelos.csv` y `decision_champion.md`, incluyendo versión vigente
  al terminar, criterio y motivo. Se suben antes de cambiar alias y se confirma
  resultado después. Fallos intentan reversión; no se oculta estado remoto incierto.
- Primera evaluación real: versión 1 promovida frente al baseline (197 537.70 vs
  239 897.90). Run de decisión `3dd2551d556149c9b72ecfcc8786ad57`.
- Ejecución completa posterior: versión 2 empata costo y métricas; no promovida,
  se conserva champion versión 1. Run de decisión `6b2684c69fa845b789e4ec422713c2fd`.
  Ambos pares de artefactos se descargaron y verificaron.
- Evidencias locales: `evidencias/decision_champion.json` y
  `evidencias/evaluacion_champion_repetida.json`.
- Suite: **175 passed, 0 skipped**, tres advertencias externas. Incluye 26 tests
  unitarios de política y dos de auditoría contra MLflow, más regresión completa.
- Sin Airflow ni serving/actualización del modelo en la API. Un único escritor
  de promociones; si cambia periodo/insumos, reevaluar champion antes de comparar.

### Corrección: aislamiento del tracking en pytest

- Identificada la causa: pruebas de integración apuntaban a `:5001` y ejecutaban
  registro de baseline/decisiones sobre NovaMercado real en cada repetición.
- `tests/conftest.py` configura tracking y Registry temporales; integración HTTP
  usa servidor propio por sesión con SQLite, artefactos y datos sintéticos. No
  requiere IDs/modelos/insumos del producto ni inventario de su migración.
- Guardas bloquean clientes externos y sustituyen variables heredadas, incluso
  si el shell configura el tracking/Registry principal. No se cambia lógica de
  registro/auditoría de ejecuciones reales ni se borran runs/modelos existentes.
- **180 passed, 0 skipped**, tres advertencias externas. Suite ejecutada con las
  variables del shell apuntando deliberadamente al servicio principal para probar
  la barrera. Pruebas de contrato no requieren servidor MLflow activo.
- Verificación de inventario principal antes/después: **14 runs → 14 runs**,
  mismos IDs, estados, parámetros, métricas, tags, modelos, versiones y aliases.
  Champion permanece versión 1; versiones 1 y 2 conservadas. Cero escrituras de
  pytest en el tracking principal. Evidencia: `evidencias/aislamiento_mlflow.json`.

### Serving del champion

- POST `/v1/prediccion` usa el pyfunc champion del Registry. Caché en memoria por
  aplicación con versión del mismo snapshot; refresco cada 30s sin bloquear las
  predicciones ya cargadas. Errores de red/carga conservan el modelo anterior.
- Features de histórico local y observaciones PostgreSQL en `[D-56, D)`, DB
  prevalece sobre CSV; promoción de D desde solicitud. No se usan ventas de D ni
  futuras. Se rechazan fechas <= corte de entrenamiento/calibración del modelo.
- Versiones/predicciones quedan persistidas antes de HTTP 200. Sin modelo inicial
  o DB disponible se responde 503; sin resultados inventados.
- **192 passed, 0 skipped**, siete advertencias de dependencias/entorno. Doce
  nuevas pruebas incluyen SQL + pyfunc reales en tracking aislado, coherencia de
  versión, correcciones, errores, refresco concurrente y continuidad con fallo MLflow.
- Comprobación de lectura del champion real versión 1: HTTP 200 para dos familias,
  cuatro predicciones persistidas en PostgreSQL temporal tras dos solicitudes,
  segunda tras simular fallo de transporte MLflow; mismo resultado y versión.
  Runs principales 14 → 14 y alias sin cambios. Evidencia:
  `evidencias/prediccion_champion.json`.
- R22 avanza con caída simulada de transporte; interrupción real del contenedor
  y tiempos de salud quedan pendientes para operación. Sin Airflow ni reentrenamiento.

### Fase 5 — DAG Airflow 3.3.2

- DAG manual `novamercado_reentrenamiento`: tareas entrenar/evaluar y decidir
  champion; la segunda requiere éxito de la primera. Un run activo, sin cron ni
  reintentos; timeout global 10 minutos. No se agregaron endpoints administrativos.
- Snapshot consistente del PostgreSQL del producto, reconciliado por clave con
  histórico CSV; observaciones prevalecen sin duplicar. Promociones nuevas se
  recuperan de solicitudes canónicas o quedan ausentes, nunca inventadas.
- Reutiliza HGB, validación temporal y política 1%/5%/10% en MLflow 3.17.2. Se
  reevalúa el champion congelado sobre los mismos datos/fechas, sin alterar sus
  runs históricos. Los dos artefactos de decisión siguen presentes por evaluación.
- Compose actualizado a api-server, scheduler y dag-processor de Airflow 3.3.2;
  imagen propia con base fija y virtualenv ML separado, credenciales externas,
  metastore PostgreSQL independiente y volúmenes de trabajo/auth persistentes.
- Pruebas con SDK/core Airflow 3.3.2 real: parseo, serialización, dag.test exitoso,
  repetición con empate de costo que conserva champion y entrenamiento fallido
  que deja promoción upstream_failed. PostgreSQL real y MLflow aislados.
- **203 passed, 0 skipped**, once advertencias externas; pip check de ambos
  entornos y `docker compose config --quiet` correctos. Los tres escenarios de
  ejecución usan 100 filas históricas sintéticas y 66 observaciones, snapshot 166.
- Tracking principal sin cambios: 14 runs, versiones 1/2 y champion 1 conservados.
  Evidencia: `evidencias/airflow_fase5.json`.
- No se construyó ni arrancó el stack Airflow de Compose. Quedan pendientes la
  validación operativa en contenedores, endpoints administrativos y mediciones
  de tiempos/actualización de la API tras DAG dentro del stack completo.

### Arranque limitado de Airflow por Docker Compose

Con autorización del usuario se construyó la imagen 3.3.2 y se levantaron solo
airflow-db, airflow-init, airflow-apiserver, airflow-dag-processor y airflow-scheduler.
Inicialización terminó con código 0; DB, API y scheduler healthy. UI HTTP 200 en
`http://127.0.0.1:8080`, autenticación comprobada, DAG
`novamercado_reentrenamiento` registrado por CLI y API, sin errores y pausado.
Conteo de dag_run: 0. No se ejecutaron reentrenamientos ni se borraron volúmenes;
API/base del producto no iniciadas y MLflow preexistente conservado.
Credenciales locales de Airflow generadas en `.env` (ignorado y protegido), sin
incluir secretos en evidencia: `evidencias/airflow_arranque.json`.


### Fase 5 — Endpoints administrativos

Implementados POST /admin/reentrenar (202/503) y GET /admin/reentrenar/{id}
(200/404/503), con adaptador REST v2 Airflow 3.3.2 y resultado terminal en XCom.
Pruebas: 233 passed, 2 deselected; las excluidas entrenan modelos. Comprobación
focalizada posterior: 36 passed. Compose válido. Sin reentrenamientos reales:
Airflow mantiene 0 DagRuns; NovaMercado conserva 14 runs y champion versión 1.
R15 validado mediante Airflow simulado; integración operativa de trigger y R16
quedan pendientes de autorización para ejecutar un reentrenamiento real.


### Fase 5 — Modelo y salud

Implementados /modelo y /health según PDF. Carga inicial no bloqueante en
lifespan, refresco máximo 30 s, snapshot servido consistente, continuidad ante
caída MLflow. Sondas paralelas DB/MLflow/Airflow y estado degradado con motivo.
Verificación HTTP con fuente simulada e intervalo real: actualización en 30.04 s
sin reinicio (límite 120 s). Caída/recuperación comprobadas con sondas simuladas.
Pytest: 246 passed, 10 skipped por falta de TEST_PRODUCT_DB_DSN, 2 deselected
para no ejecutar reentrenamientos. No se modificó MLflow principal ni se ejecutaron
DAGs. Evidencia: evidencias/modelo_salud.json. Bootstrap y tiempos del stack
completo desde cero permanecen pendientes.


### Fase 6 — Bootstrap automático y persistencia

Servicio product-init con migración idempotente, carga/validación inicial CSV,
entrenamiento HGB existente solo sin champion y promoción mediante política
existente. Lock y checkpoint en model-cache; API depende de éxito del init y
scheduler saludable, con healthcheck que exige estado ok.

Imagen construida; dos verificaciones operativas en modo --solo-reutilizar
confirmaron champion 1. Se reiniciaron PostgreSQL producto, API y MLflow sin
borrar volúmenes; API recuperó health ok, Registry conserva 14 runs y champion 1.
La DB operativa estaba vacía (0 solicitudes/observaciones/predicciones antes y
después); registros de negocio comprobados en PostgreSQL aislado mediante pytest.
Airflow conserva 0 DagRuns. No se ejecutaron reentrenamientos reales.

268 passed, 0 skipped, 2 deselected (pruebas que ejecutan DAG de entrenamiento).
Corregida fixture de integración para configurar modelo/datos antes del lifespan
y respetar intervalo máximo 30 s. Evidencia: evidencias/bootstrap_fase6.json.
Pendientes: primer entrenamiento real desde Registry vacío, readiness <=10 min
en stack limpio y ciclo DAG completo. No se vaciaron volúmenes para verificarlos.
