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
| R01 | Pronóstico por tienda, familia y fecha, con venta esperada y sugerido | 1, 6 | POST real con varios ítems: campos y valores correctos | Pendiente |
| R02 | Políticas coherentes para reparar, advertir o rechazar defectos, también no catalogados | 1–2 | Pruebas parametrizadas con ejemplos y nuevos casos | Pendiente |
| R03 | Las respuestas explican correcciones/advertencias | 2, 6 | Verificar `calidad.estado` y observaciones | Pendiente |
| R04 | Contrato exacto de API con Pydantic y limpieza fuera de endpoints | 2, 6–7 | Pruebas de esquema, estructura de código y 422 | Pendiente |
| R05 | pytest del contrato independientes de un MLflow activo | 2 | Ejecutar suite con MLflow apagado/mockeado | Pendiente |
| R06 | PostgreSQL de producto distinto al de Airflow, en Docker | 3 | Comprobar separación y conexiones con Compose | Pendiente |
| R07 | Persistir solicitudes, predicciones, correcciones, observaciones y versión por predicción | 1, 3 | Consultar DB tras solicitudes y reinicio | Pendiente |
| R08 | Observaciones idempotentes | 3, 7 | Reenvío idéntico: HTTP 200 y `registros_guardados: 0`; sin duplicados | Pendiente |
| R09 | Baseline y al menos un modelo ML que mejore al baseline | 3 | Evaluación temporal documentada y reproducible | Pendiente |
| R10 | Métricas técnicas y costos de negocio basados en `costos.csv` | 2–3 | Comparativa calculada con fórmula del PDF | Pendiente |
| R11 | Cantidad sugerida coherente con costo por familia | 2–3 | Casos con distintas relaciones de costos y explicación | Pendiente |
| R12 | Experimentos, modelos, linaje y alias vigente en MLflow Registry | 3 | Capturas/consultas de runs, artefactos, versiones y alias | Pendiente |
| R13 | Criterio automatizado y explícito de promoción | 3 | Pruebas con mejora, empate, retroceso y error | Pendiente |
| R14 | Airflow reentrena usando histórico y observaciones persistidas | 3 | DAG ejecutado, consulta a DB y evidencia de ejecución | Pendiente |
| R15 | Reentrenamiento invocable por API y estado consultable | 3, 7 | POST 202/503, GET estados y GET 404 | Pendiente |
| R16 | Modelo promovido se usa en API sin reinicio ≤2 min tras el DAG | 3 | Comparar versiones antes/después con tiempo registrado | Pendiente |
| R17 | Fallo o candidato descartado no afecta modelo vigente | 3 | Simular fallo y no promoción; continuidad de predicciones | Pendiente |
| R18 | Todo se levanta con `docker compose up` y servicio llamado `mlflow` | 3 | `docker compose config`, `up`, `ps`, curl | Pendiente |
| R19 | Primer arranque: carga datos y entrena/registra modelo automáticamente | 3 | Arrancar con volúmenes vacíos y sin intervención | Pendiente |
| R20 | Arranque posterior: conservar estado, no repetir bootstrap | 3 | Reiniciar sin borrar volúmenes; comparar versiones/datos | Pendiente |
| R21 | Versiones fijas de imágenes; ni credenciales ni datos en imagen/repositorio; `.env.example` | 3 | Revisar Compose, Dockerfiles y `git ls-files` | Pendiente |
| R22 | API sigue prediciendo con modelo cargado si MLflow cae | 3 | Interrumpir MLflow; POST predicción debe funcionar | Pendiente |
| R23 | `/health` degradado en <1 min de caída, ok en <2 min de retorno | 3 | Prueba cronometrada de caída/recuperación | Pendiente |
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
