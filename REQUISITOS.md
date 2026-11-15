# NovaMercado — Especificación de Requisitos y Criterios de Aceptación

**Producto:** servicio de pronóstico diario de ventas por tienda y familia.

**Estado:** requisitos, criterios de aceptación y evidencias se mantienen en la matriz vigente. Los archivos de entrada residen en `data/` y se excluyen de Git. Este documento también conserva la bitácora histórica de validaciones.

> **Trazabilidad:** cada requisito se vincula a una prueba o evidencia antes de declararse verificado. La descripción de un archivo o mecanismo **no sustituye** la prueba de que funciona.

## 1. Alcance y criterios de diseño

Construir un producto ejecutable con FastAPI, PostgreSQL, MLflow, Airflow y Docker Compose que:

1. Reciba pronósticos diarios de unidades vendidas por tienda, fecha y familia, devolviendo `venta_esperada` y `cantidad_sugerida`.
2. Tolere entradas defectuosas con políticas justificadas de **reparar, advertir o rechazar**, sin inventar silenciosamente datos.
3. Persista las solicitudes, predicciones, correcciones y ventas reales observadas; mantenga la versión usada para cada predicción.
4. Entrene un modelo inicial de manera autónoma, reentrene con datos nuevos y promueva nuevos modelos solo cuando satisfagan un criterio verificable.
5. Permanezca operativo ante interrupciones temporales de MLflow, preserve estado entre reinicios y pueda ejecutarse con el procedimiento documentado.

**Prioridad:** primero contrato, calidad, persistencia y operación robusta; después mejorar el pronóstico sin comprometer límites de tiempo.

### Clasificación de requisitos

- **[REQUISITO] Obligatorio:** forma parte del contrato de producto.
- **[IMPLEMENTACIÓN] Necesario según la arquitectura:** elección técnica para cumplir el requisito, no una restricción de nombre de archivo.
- **[OPCIONAL] Mejora:** solo si aporta valor y no compromete plazos.

## 2. Datos de entrada

El contrato de datos requiere estos archivos. Los insumos operativos están en `data/`; su contenido queda excluido de Git. El entorno de despliegue debe disponer allí de los archivos de entrada:

| Insumo | Uso previsto | Estado |
|---|---|---|
| `tiendas.csv` | Catálogo de tiendas, formatos y ciudades | Disponible localmente; ignorado por Git |
| `familias.csv` | Catálogo de familias y normalización de IDs | Disponible localmente; ignorado por Git |
| `historico_ventas.csv` | Dos años de ventas diarias y `en_promocion` por tienda/familia | Disponible localmente; ignorado por Git |
| `feriados.csv` | Feriados nacionales/locales, fechas comerciales y de pago, incluidos días futuros | Disponible localmente; ignorado por Git |
| `costos.csv` | Costos relativos de faltantes/sobrantes por familia | Disponible localmente; ignorado por Git |
| `catalogo_errores.md` | Ejemplos y tipos de problemas observados; no exhaustivo | Disponible localmente; ignorado por Git |
| `ejemplos/` | Solicitudes válidas y defectuosas | Disponible localmente; ignorado por Git |

**Reglas de integración de los datos:**
- En `feriados.csv`, `ambito` vale `nacional` o el nombre de ciudad que coincide con `ciudad` en `tiendas.csv`.
- El sistema recibe observaciones de ventas del día anterior **antes** del pronóstico del día siguiente.
- Las observaciones **no** contienen promociones; `en_promocion` del día de pronóstico llega en la solicitud.
- No usar el reloj real para invalidar fechas: el servicio opera con **fechas simuladas**; la evaluación es posterior al histórico y está cubierta por el calendario de feriados.
- El operador de despliegue coloca los insumos en la ruta indicada en README. El primer arranque debe funcionar a partir de esos archivos.

La inspección de cabeceras, tipos, rangos, nulos, duplicados, claves y ejemplos se documentó antes de implementar reglas. Repetirla cuando cambien los archivos fuente.

## 3. Matriz de requisitos y pruebas de aceptación

**Estado actualizado al 2026-11-15.** `Verificado` requiere prueba/evidencia indicada. `Parcial` significa que existe implementación o un escenario limitado, pero falta la aceptación completa. `Pendiente` no se afirma como cumplido. La revisión documental Fase 8.2 no vuelve a ejecutar verificaciones.

| ID | Requisito | Prueba o evidencia de aceptación | Estado |
|---|---|---|---|
| R01 | Pronóstico por tienda, familia y fecha, con venta esperada y sugerido | Serving champion real versión 1, dos familias y persistencia; `evidencias/prediccion_champion.json` y pruebas aisladas | Verificado |
| R02 | Políticas coherentes para reparar, advertir o rechazar defectos, también no catalogados | `tests/test_normalizacion.py`: ejemplos de entrada y casos adicionales | Verificado con pytest aislado |
| R03 | Las respuestas explican correcciones/advertencias | Pruebas de normalización y HTTP verifican `calidad.estado` y detalle | Verificado |
| R04 | Contrato exacto de API con Pydantic y limpieza fuera de endpoints | Esquemas Pydantic, calidad separada y pruebas HTTP 422 | Verificado por pruebas/código |
| R05 | pytest del contrato independientes de un MLflow activo | 177 pruebas focalizadas con URI MLflow heredado inalcanzable y stores temporales | Verificado |
| R06 | PostgreSQL de producto distinto al de Airflow, en Docker | Compose aislado: servicios product-db y airflow-db independientes; integraciones DB | Verificado en Compose aislado |
| R07 | Persistir solicitudes, predicciones, correcciones, observaciones y versión por predicción | SQL tras reinicio de PostgreSQL Compose aislado; `evidencias/auditoria_p1.json` | Verificado en Compose aislado |
| R08 | Observaciones idempotentes | `tests/test_persistencia.py`: HTTP 200, reenvío 0, nuevos + modificados, concurrencia sin duplicados; evidencia en `evidencias/fase_3_1_postgresql.md` | Verificado |
| R09 | Baseline y al menos un modelo ML que mejore al baseline | `evidencias/comparacion_histgradient.json`: mismo periodo/casos, HGB mejora MAE/RMSE/WAPE/costo; `tests/test_histgradient.py` | Verificado offline |
| R10 | Métricas técnicas y costos de negocio basados en `costos.csv` | MAE/RMSE/WAPE/costo mismo periodo/casos, `comparacion_histgradient.json` | Verificado offline |
| R11 | Cantidad sugerida coherente con costo por familia | Tests de costos asimétricos/cuantiles y evaluación por familia | Verificado por pruebas/evaluación |
| R12 | Experimentos, modelos, linaje y alias vigente en MLflow Registry | Consulta Registry/run/artifacts solo lectura, `evidencias/auditoria_p1.json` | Verificado |
| R13 | Criterio automatizado y explícito de promoción | `ml/promocion.py`, `tests/test_promocion.py`, `tests/test_promocion_mlflow.py`: mejora, empate, retroceso y error; decisiones auditadas | Verificado |
| R14 | Airflow reentrena usando histórico y observaciones persistidas | POST/GET y DAG real con PostgreSQL/MLflow aislados; `evidencias/fase7_integral.json` | Verificado en Compose aislado |
| R15 | Reentrenamiento invocable por API y estado consultable | Contrato simulado y POST 202/GET terminal reales en Compose aislado | Verificado |
| R16 | Modelo promovido se usa en API sin reinicio ≤2 min tras el DAG | Promoción real 1→2, predicción con versión 2 en 13,24 s desde fin DAG, mismo contenedor | Verificado en Compose aislado |
| R17 | Fallo o candidato descartado no afecta modelo vigente | Pruebas de fallos/promoción y Compose aislado conserva versión 1 tras descarte | Verificado |
| R18 | Todo se levanta con `docker compose up` y servicio llamado `mlflow` | Compose aislado: stack completo, API health ok; `evidencias/fase7_integral.json` | Verificado en Compose aislado |
| R19 | Primer arranque: carga datos y entrena/registra modelo automáticamente | Registry vacío y bootstrap real en Compose aislado; evidencias/fase7_integral.json | Verificado |
| R20 | Arranque posterior: conservar estado, no repetir bootstrap | Reinicio real API/DB/MLflow; 14 runs y champion 1; checkpoint y concurrencia probados | Verificado con champion existente |
| R21 | Versiones fijas de imágenes; ni credenciales ni datos en imagen/repositorio; `.env.example` | Revisión estática Compose/Dockerfiles, ignore y archivos versionados | Verificado por revisión estática |
| R22 | API sigue prediciendo con modelo cargado si MLflow cae | stop MLflow aislado, 15 predicciones idénticas versión 2 y refresco fallido observado | Verificado en Compose aislado |
| R23 | `/health` degradado en <1 min de caída, ok en <2 min de retorno | stop/start real MLflow: degradado 1,38 s, ok 29,03 s; evidencia Fase 7 resiliencia | Verificado en Compose aislado |
| R24 | Salud `ok` ≤10 min del arranque (sin contar build) | Registry vacío, volúmenes nuevos, health ok en 65,16 s; evidencia Fase 7 | Verificado en Compose aislado |
| R25 | Reentrenamiento finaliza ≤10 min | POST/GET real con Airflow 3.3.2: 28,71 s, exitoso sin promoción | Verificado en Compose aislado |
| R26 | README desde cero y ubicación de insumos | Clon limpio `origin/dev` (`ae44fd7`), bootstrap/health/modelo/persistencia tras reinicio; `evidencias/r26_clone_origin_dev.json` | Verificado con adaptaciones de aislamiento documentadas |
| R27 | Archivo de contexto para agente (`AGENTS.md`, `CLAUDE.md` o similar) | `AGENTS.md` actualizado en Fase 8.2 | Verificado documentalmente |
| R28 | `DECISIONES.md` documenta políticas, variables, sugerido, promoción, alternativas | Secciones de datos/calidad, variables y alternativas de `DECISIONES.md`; revisión documental Fase 8.3 | Verificado documentalmente |
| R29 | Repo GitHub accesible y tag exacto `entrega-lab2` anterior al límite | Verificar remoto, `git show entrega-lab2` y fecha; `git ls-remote` confirmó acceso público y destino en `main` | Verificado: tag apunta a `bbda0ccbcd005f49db05e1442f80d409189d2b03` |
| R30 | Evidencias MLflow, DAG y respuestas válidas/defectuosas | MLflow/DAG en evidencias de Fases 4–7; ejemplos 200/422 con request/response y procedencia en `evidencias/respuestas_api.json` | Verificado documentalmente; capturas HTTP contractuales usan dobles explícitos |
| R31 | Evaluación simula errores inéditos, drift, caídas y reinicios | `evidencias/r31_operacion_extendida.json`: 140 días, 12 respuestas 422 no catalogadas, 4 reentrenamientos, reinicios, MLflow interrumpido/recuperado y principal intacto | Verificado en Compose aislado; datos sintéticos |

### 3.1 Contrato externo de la API

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

**Nota de pruebas:** pueden existir campos adicionales en respuestas, pero no se pueden omitir ni renombrar los campos del contrato.

### 3.2 Fórmula y restricciones temporales

Costo por tienda, familia y día:

```text
costo = c_faltante * max(real - sugerido, 0)
      + c_sobrante * max(sugerido - real, 0)
```

- Las ventas se expresan **en unidades**.
- Al emitir un pronóstico de día D, solo se conocen observaciones de **días anteriores**.
- La promoción del día D viene de la solicitud de pronóstico y no de observaciones.
- Los feriados locales se aplican según ciudad; validar datos de feriados futuros sin extrapolar indebidamente.
- Validaciones temporales de entrenamiento y selección deben impedir fuga de información.

## 4. Decisiones iniciales de arquitectura — histórico, sustituido por la implementación final

Esta sección conserva las hipótesis de planificación previas a inspeccionar los datos y desarrollar el sistema. **No describe el estado implementado ni es fuente de la matriz.** Para decisiones finales, variables y justificaciones vigentes, consultar `DECISIONES.md`; para cumplimiento, usar exclusivamente la sección 3 y las evidencias enlazadas.

| Tema | Propuesta | Clasificación | Confirmar con datos |
|---|---|---|---|
| Orquestación local | `compose.yaml` con API, DB producto, MLflow y Airflow y sus dependencias | IMPLEMENTACIÓN (Compose sí obligatorio; nombre `.yaml` no) | No |
| Entrenamiento inicial | Servicio/tarea de bootstrap idempotente, coordinado por Compose | IMPLEMENTACIÓN | Sí, rendimiento |
| PostgreSQL | DB producto independiente de DB/metastore de Airflow | REQUISITO | No |
| Configuración | `.env.example` sin secretos; variables desde `.env` local ignorado | REQUISITO + IMPLEMENTACIÓN | No |
| FastAPI | Routers, esquemas Pydantic, servicios de limpieza separados | REQUISITO + IMPLEMENTACIÓN | Sí, errores reales |
| Pronóstico | Baseline simple estacional + un modelo ML global con rasgos de tienda/familia, calendario y promociones | IMPLEMENTACIÓN; baseline y ML son requisitos | Sí |
| Algoritmo | Probar HistGradientBoosting o CatBoost, sin decidir antes del EDA | IMPLEMENTACIÓN | Sí |
| Cantidad sugerida | Estimar un cuantil de demanda basado en costos si existe distribución/estimación fiable; si no, calibración validada por costo | IMPLEMENTACIÓN; coherencia de costos es requisito | Sí |
| Registro | Persistir versión por cada predicción, valores de entrada corregidos y advertencias; mantener observaciones idempotentes | REQUISITO + IMPLEMENTACIÓN | No |
| Modelo activo | Alias estable en MLflow Registry y caché local/artefacto cargado en memoria | REQUISITO + IMPLEMENTACIÓN | No |
| Refresco automático | Verificar alias/versión periódicamente, con frecuencia que garantice <2 min | IMPLEMENTACIÓN | No |
| Sin MLflow | Predicciones con modelo ya cargado; salud degradada y recuperación comprobables | REQUISITO | No |
| Promoción | Elegir candidato solo si reduce costo validado frente al vigente y supera controles de calidad y estabilidad | IMPLEMENTACIÓN; criterio explícito automatizado es requisito | Sí |
| Reentrenamiento | DAG disparado mediante endpoint administrativo; observa datos persistidos y no bloquea API | REQUISITO + IMPLEMENTACIÓN | No |
| Git | Commits de release y tag `entrega-lab2` sobre la versión aceptada | REQUISITO + IMPLEMENTACIÓN | No |

**Cuidados técnicos:**
- El servicio `mlflow` debe llamarse exactamente así en Compose.
- **No** descargar un modelo de MLflow en cada predicción; conservar modelo cargado y disponer de estrategia de actualización y recuperación.
- Persistir los artefactos del modelo y la metadata de MLflow para sobrevivir reinicios; validar que API y Registry no diverjan.
- Los datos y secretos reales no deben entrar en Git ni en imágenes. Usar `.gitignore`, `.dockerignore` y montajes de volumen/configuración externa.
- Evitar complejidad innecesaria (varios modelos por cada tienda/familia) antes de medir el beneficio.
- La propuesta de cuantil `c_faltante / (c_faltante+c_sobrante)` es una **decisión de modelado condicionada a una distribución predictiva adecuada**, no una exigencia textual ni garantía automática de mejora.

## 5. Estructura inicialmente propuesta — histórico

La estructura de esta sección fue una propuesta de arranque. Las rutas actuales pueden diferir; consultar `AGENTS.md` y el árbol del repositorio. Las obligaciones y el estado vigente están en la matriz de la sección 3.

| Ruta propuesta | Propósito | Naturaleza |
|---|---|---|
| `README.md` | Levantar desde cero, ruta de insumos, ejecución, pruebas y evidencias | Requisito documental |
| `DECISIONES.md` | Políticas, alternativas, justificaciones del modelo, sugerido y promoción | Requisito documental |
| `AGENTS.md` | Contexto, objetivos e instrucciones de desarrollo | Requisito documental; nombre elegido |
| `.env.example` | Variables necesarias sin secretos | Requisito documental |
| `compose.yaml` | Describir servicios y dependencias de Docker Compose | IMPLEMENTACIÓN para cumplir Compose; **no** exigir archivos YAML arbitrarios |
| `Dockerfile`, `airflow/Dockerfile` | Construcción de imágenes propias | IMPLEMENTACIÓN si se requieren |
| `requirements.txt` (u otro lock/gestor) | Dependencias reproducibles | IMPLEMENTACIÓN |
| `.gitignore`, `.dockerignore` | Excluir secretos, datos y artefactos no permitidos | IMPLEMENTACIÓN |
| `app/` | Endpoints, esquemas, lógica de calidad, servicios, DB | El producto requiere código; organización propuesta |
| `ml/` | Entrenamiento, features, predicción, evaluación, Registry | El producto requiere modelos; organización propuesta |
| `airflow/dags/reentrenamiento.py` | DAG de reentrenamiento | El producto requiere DAG; ruta y nombre propuestos |
| `tests/` | pytest del contrato, calidad, DB, operación | Requisito de pruebas; rutas propuestas |
| `data/` | **Carpeta vacía/documentada** para archivos de entrada | IMPLEMENTACIÓN; contenido local |
| `evidencias/` | Capturas/logs/ejemplos validados | Requisito de trazabilidad; ruta propuesta |
| `config/modelo.yaml`, `config/calidad.yaml` | Configuración opcional del modelo/reglas | OPCIONAL; no exigidos |
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
├── data/                     # Archivos de entrada locales; no subir datos al repo
├── tests/
└── evidencias/
```

**La estructura es provisional:** tras inspeccionar insumos y versiones elegidas, se puede ajustar sin alterar obligaciones externas.

## 6. Plan de implementación y criterios de salida

**Modo de trabajo:** una fase por cambio, alcance acotado, pruebas, revisión de diferencias y actualización de la matriz. No modificar requisitos del contrato sin justificarlo.

### Fase 0 — Auditoría previa (sin implementar lógica)
- Leer `REQUISITOS.md` y los archivos de entrada disponibles.
- Crear/actualizar matriz de cumplimiento y lista de casos de prueba, identificando dependencias.
- Distinguir explícitamente obligaciones y opciones; identificar contradicciones o datos faltantes.
- **Salida:** matriz revisada y plan de pruebas; ninguna suposición sobre contenido de CSV no recibidos.

### Fase 1 — Esqueleto, entorno y Compose mínimo
- Crear repositorio y `AGENTS.md`, `README.md` inicial, `.env.example`, ignore files, estructura modular.
- Crear `compose.yaml` con servicio `mlflow` y diseños claros de DB producto y metastore Airflow.
- Fijar versiones de imágenes y librerías de forma reproducible; parametrizar credenciales.
- **Salida:** `docker compose config --quiet` sin errores; estructura auditable; ninguna contraseña ni dato de origen versionado.

### Fase 2 — Contrato FastAPI y política de calidad
- Implementar los endpoints del contrato y esquemas Pydantic; normalización/limpieza en módulos independientes.
- Documentar reglas reparar/advertir/rechazar por tipo de problema, de modo extensible.
- Montar tests unitarios de API con dependencias simuladas (sin MLflow).
- **Salida:** pytest independiente de MLflow y respuestas estructuralmente idénticas al contrato (funcionalidad de ML inicialmente simulada).

### Fase 3 — Persistencia e idempotencia
- Implementar tablas/consultas y migraciones o inicialización controlada en PostgreSQL producto.
- Guardar entrada original/canónica, acciones de calidad, predicción con versión y ventas observadas.
- Manejar nuevas observaciones, correcciones y duplicados; idempotencia por clave natural.
- **Salida:** tests de persistencia y reenvío idéntico con 0 cambios; datos sobreviven reinicio.

### Fase 4 — Entrenamiento, costo e MLflow
- Con datos de operación reales, EDA enfocado en integridad y separación temporal.
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
- Bootstrap automático desde archivos de entrada cuando no hay modelo; no repetir en siguientes arranques.
- Healthchecks de dependencias y recuperación de MLflow.
- Pruebas de caída de MLflow (predicción continúa), health degradado <1 min, ok <2 min tras retorno.
- **Salida:** `docker compose up` desde limpio, `/health` ok ≤10 min sin build; cada reentrenamiento ≤10 min; persistencia post-reinicio.

### Fase 7 — Documentación y evidencias
- Completar README desde cero, `DECISIONES.md`, esquema de datos y guía de uso/diagnóstico.
- Capturar experimentos/Registry de MLflow, ejecuciones DAG y ejemplos de API buenos/defectuosos.
- Ejecutar simulación diaria de observación D−1 → predicción D, fechas futuras, cambios de demanda.
- **Salida:** un tercero puede clonar, colocar insumos y ejecutar sin intervención manual.

### Fase 8 — Auditoría y aceptación operativa
- Revisar **cada** R01–R31 con archivo, prueba y evidencia, cerrando desviaciones.
- Verificar ausencia de secretos/datos en Git, versiones fijas y nombre exacto `mlflow`.
- Probar reinicio sin eliminar volúmenes, caída/retorno de MLflow y actualización sin reinicio.
- Crear el tag de versión `entrega-lab2` sobre el commit aceptado; comprobar referencia remota y acceso público.
- Publicar el enlace del repositorio según el proceso de liberación establecido.
- **Salida:** matriz trazable y release reproducible.

## 7. Pruebas de aceptación operativa (simulación de punta a punta)

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

## 8. Política de ingeniería y control de cambios

- Mantener el alcance de NovaMercado separado de otros productos y repositorios.
- Por cada fase: plan pequeño → cambios → tests → revisión → commit → actualizar matriz.
- No afirmar que algo pasó sin ejecutar comandos o mostrar evidencia.
- No cambiar nombres de campos, rutas o códigos del contrato por conveniencia.
- Registrar en `DECISIONES.md` alternativas evaluadas y razones; no inventar resultados experimentales.
- No versionar archivos de datos de origen; el entorno los suministra localmente y no se copian a las imágenes.
- Si faltan datos, implementar únicamente componentes que no dependan de observar los archivos reales; **no simular un esquema supuesto como definitivo**.
- Elegir herramientas y modelos con tiempos de arranque/entrenamiento dentro de los límites impuestos.

## 9. Riesgos iniciales — nota histórica superada

La tabla siguiente registra asuntos identificados antes del desarrollo, varios ya resueltos o revaluados. No usarla como estado actual. La sección 3 es la referencia vigente.

| Tema | Acción posterior |
|---|---|
| Archivos de entrada no disponibles | Disponer de los siete insumos e inspeccionarlos antes de definir políticas o entrenar |
| Catálogo de errores no exhaustivo | Definir reglas generales y pruebas adversariales, no solo copiar ejemplos |
| Datos históricos/observaciones potencialmente superpuestos | Definir reconciliación por clave y no duplicar entrenamiento |
| Métrica de costo y sugeridos | Validar según costos reales por familia, no usar heurística sin comprobar |
| Cambio de patrón de demanda | Evaluación temporal y reentrenamiento con observaciones recientes |
| Latencia de actualización del modelo | Cache y refresco comprobado con reloj/tiempos de prueba |
| Recuperación tras fallo MLflow | Asegurar que un modelo ya cargado sigue disponible; cache/artefactos persistidos |
| Tiempo máximo 10 min | Medición bajo infraestructura real; limitar candidatos y ejecución del DAG |
| Ventana de operación | Confirmar límites de ejecución en el entorno objetivo |
| Ambigüedad de reglas puntuales de limpieza | Resolver con inspección de datos y registrar políticas explícitas en `DECISIONES.md` |

## 10. Snapshot inicial de estado — histórico, superado

Las casillas y la siguiente acción de esta sección corresponden al inicio del proyecto. Ya no representan el estado actual; consultar la sección 3 y las actualizaciones fechadas.

- [x] Requisitos funcionales y operativos documentados.
- [x] Especificación y matriz de aceptación documentadas.
- [ ] Archivos de entrada disponibles localmente.
- [ ] Repositorio inicializado.
- [ ] Fase 0 de preparación ejecutada.
- [ ] Implementación y evidencias.
- [ ] Auditoría final y tag `entrega-lab2`.

**Nota histórica:** este snapshot describe el estado previo al inicio de la implementación. Para el estado vigente, consultar la matriz de requisitos y las evidencias enlazadas.

## 11. Bitácora histórica de avance

Las subsecciones fechadas son registros de lo que se sabía y verificaba en cada
fase; pueden contener estados y pendientes que luego cambiaron. No eliminarlas
ni usarlas para determinar cumplimiento actual. Contrastar avances posteriores
con la matriz de la sección 3 y sus evidencias enlazadas.

### Snapshot — 2026-11-14

Esta actualización sustituye los estados iniciales anteriores sobre disponibilidad
de insumos y repositorio: Git ya está inicializado con remoto `origin`; los cinco
CSV, catálogo y ejemplos están en `data/` (tras moverlos desde `../datos_lab2/`)
y se han inspeccionado. Su contenido está ignorado por Git salvo `.gitkeep`;
Compose y `.env.example` usan `./data` por defecto.
La especificación funcional se contrastó nuevamente y no se encontraron discrepancias sustanciales.

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
  incluidos los 12 ejemplos de entrada. Sin servidor ni paquete MLflow.
- R02–R05 y R28 avanzan parcialmente; siguen pendientes la integración HTTP,
  las respuestas completas y las pruebas de endpoints. R08 no se declara cerrado:
  la idempotencia persistida pertenece a Fase 3.
- Sin persistencia, modelos, DAG, construcción ni arranque de contenedores.

### Fase 2.2 — Endpoints de predicción y observaciones

- Implementados ambos POST del contrato, reutilizando normalización, con esquemas
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

Implementados `/modelo` y `/health` según el contrato de producto. Carga inicial no bloqueante en
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


### Fase 7 — Aceptación integral aislada

Runner opt-in `scripts/verificar_integral.py --ejecutar`, con credenciales nuevas
privadas en .e2e/, recursos Compose nuevos y guardas de aislamiento. Se construyeron
imágenes propias antes del cronómetro. Registry inicial sin runs ni modelos:
bootstrap real y health ok en **65,16 s** (límite 600 s).

Observación del día posterior al histórico aceptada (1), idéntica devuelve 0;
predicción del día siguiente real y versionada. POST administrativo disparó DAG
real Airflow 3.3.2; estado exitoso en **28,71 s** (límite 600 s). Candidato versión
2 sin mejora mínima del costo: conserva champion 1, con decisión auditada.
No se certifica aquí una promoción efectiva ni su propagación en el stack.

Reinicio real DB/MLflow/API conserva observación (reenvío 0), runs y modelos;
bootstrap repetido reutiliza champion y no duplica entrenamiento. Se detuvieron
solo los contenedores aislados, preservando todos sus volúmenes. Inventario
principal idéntico antes/después: mismos 14 IDs de runs, versiones y champion 1.
Evidencia: evidencias/fase7_integral.json.

Pendientes de aceptación extendida: promoción efectiva en stack y recarga <=2 min,
simulación diaria prolongada/cambio de demanda y caída/retorno MLflow en stack
completo. No se crea tag de entrega ni se publica en esta fase.

Regresión final Fase 7: **281 passed, 0 skipped**, incluidas las pruebas SDK con
DAG real sobre PostgreSQL y MLflow de pytest aislados. Inventario principal
verificado de nuevo tras pytest: sin cambios. No se borró ningún volumen.


### Fase 7 — Promoción efectiva y resiliencia completadas

Escenario sintético determinista en otro Compose aislado: 420 días históricos y
140 días posteriores con salto de demanda, predicción D → observación D antes
de predecir D+1. DAG normal, sin alterar política, métricas ni alias manualmente.
Candidato 2 promovido sobre 1: costo 717 vs 30897 con evaluación homogénea.
`/modelo` y predicción real usan versión 2 en **13,24 s** desde `end_date` del
DAG; mismo ID y StartedAt del contenedor API. Límite 120 s satisfecho.

Se detuvo solo MLflow aislado: health 200 degradado en **1,38 s** (<60 s),
15 predicciones con respuesta idéntica y versión 2; se mantuvo la caída hasta
observar refresco fallido. Tras start, health ok en **29,03 s** (<120 s), con
modelo/predicción conservados y sin reiniciar API. Reinicio posterior conserva
Registry y observaciones, bootstrap no duplica runs. Contenedores aislados
detenidos al acabar; todos los volúmenes conservados.

Inventario principal idéntico: 14 runs, mismas versiones y champion 1. Evidencias:
`evidencias/fase7_resiliencia.json`, `evidencias/fase7_promocion_comparacion.csv`,
`evidencias/fase7_promocion_decision.md`. Certifica la operación en escenario
sintético controlado; no representa una mejora predictiva en datos futuros.

Regresión final de promoción/resiliencia: **284 passed, 0 skipped** con PostgreSQL
y MLflow propios de pytest, incluidas ejecuciones SDK de DAG. Inventario principal
verificado otra vez tras pytest: idéntico (14 runs y champion 1). No quedan
pendientes las verificaciones de promoción/recarga ni caída/retorno solicitadas.


### Fase 8 — Evidencias P1 (R02–R05, R07, R10–R12, R17)

Suite focalizada en entorno aislado: **177 passed, 0 failed, 0 skipped, 2 deselected**
(los dos casos de DAG que entrenan). URI MLflow heredada apuntó a un puerto sin
servidor; fixtures de pruebas usaron stores temporales. PostgreSQL temporal de
pruebas con tmpfs fue detenido al acabar.

En la DB Compose aislada que ya contenía la prueba integral, se reinició PostgreSQL
y luego se consultó SQL: 4 solicitudes, 1 predicción, 1 acción de calidad,
1 observación, 1 historial; versión persistida 1. El servicio DB fue detenido después.
R10: 6.720 casos, 2026-01-04–2026-02-28; costo baseline 239.897,90 y HGB 197.537,70
(reducción 17,66%). R11: costo por CSV y pruebas de costos asimétricos. R12: Registry
principal consultado solo lectura: 14 runs, versiones 1/2 READY con runs FINISHED,
artefactos de código/configuración/evaluación/linaje; champion 1. Inventario igual
a evidencia previa. R17: errores y no promoción cubiertos por pruebas y ejecución
Compose aislada; candidato descartado conservó versión 1.

Detalle y conteos: `evidencias/auditoria_p1.json`. No se alteró el champion ni se
borró ningún volumen.


### Fase 8.2 — Documentación consolidada (2026-11-15)

README, AGENTS y DECISIONES se contrastaron con Compose, código y
evidencias existentes. No ejecutó pytest ni contenedores. La matriz de la
sección 3 es la única tabla de cumplimiento vigente.

### Fase 8.3 — Cierre documental de R28/R30 (2026-11-15)

Se completó `DECISIONES.md` con el inventario de variables de `.env.example`,
alternativas consideradas y razones de las decisiones finales. Se agregaron
capturas 200/422 de ambas rutas de negocio en `evidencias/respuestas_api.json`;
el archivo distingue respuestas HTTP obtenidas con dobles de contrato y una
predicción observada en Compose aislado con su modelo y escenario sintético.
Los registros de observaciones y de DAG/MLflow se conservan en las evidencias
de Fases 3 y 7. R28 y R30 quedan verificados documentalmente bajo esos límites.

README ahora recomienda esperar/reintentar `/health` hasta `estado=ok` (máximo
10 minutos) y consultar logs al vencer. Las secciones 4, 5, 9, 10 y las notas
fechadas de fases previas se identifican como decisiones iniciales, snapshots
históricos o bitácora, no como estado actual. Evidencias históricas que indiquen
pendientes posteriormente cerrados no se borran: su fecha y evidencia posterior
permiten reconocerlas como superadas.

Esta fase fue documental y de captura local del contrato HTTP con TestClient;
no ejecutó pytest, Docker, reentrenamiento ni alteró MLflow/DB. Siguen abiertos
R26 (clon limpio), R29 (tag y acceso remoto) y R31 (simulación extendida de
errores inéditos/drift). La parte R30 de errores HTTP queda respaldada por las
capturas de contrato, no por respuestas de un servicio desplegado.

### Fase 8.4 — Simulación extendida R31 (2026-11-15)

Runner `scripts/verificar_integral.py --ejecutar --resiliencia` extendido y
ejecutado en proyecto nuevo `novamercado-e2e-821390f461`. Los datos sintéticos
contienen 420 días de historia estable y un salto de demanda 120→320 durante
140 días simulados. Cada día se pronosticó antes de observar la venta del mismo
día; la observación se incorporó antes del pronóstico siguiente. Se insertaron
12 rechazos HTTP 422 de tres tipos no incluidos como ejemplos concretos del
catálogo: familia nueva desconocida, venta fraccionaria y duplicado contradictorio.

Hubo reentrenamientos al completar 35, 70 y 105 días, más una evaluación final
al día 140. Todos terminaron en estado exitoso; el champion se actualizó en los
casos que mejoraron y FastAPI sirvió la versión vigente. La ejecución reinició
product-db/API al día 70, MLflow/API al día 105, y al cierre reinició
product-db/MLflow/API. También se detuvo y recuperó MLflow: salud degradada en
1,13 s, recuperación en 30,34 s y predicciones continuaron usando versión 5.
Tras el último reinicio se verificaron health ok, Registry sin duplicación de
bootstrap y reenvío idéntico de observación con 0 registros.

El reporte confirma que el inventario principal tuvo 14 runs antes/después y
conservó champion 1. Las pruebas no modificaron la política de promoción. La
primera iteración encontró y corrigió en el runner una comprobación prematura
del refresco del alias; su diagnóstico queda en
`evidencias/r31_iteracion_fallo_refresco.json` y no se considera una aceptación
fallida del producto. Resultado final completo en
`evidencias/r31_operacion_extendida.json`. Esta simulación cierra R31 para los
escenarios ejecutados, no representa el comportamiento de demanda futura ni
sustituye R26 (clon limpio) o R29 (tag y acceso remoto).

### Fase 8.5 — Prueba de clon limpio R26 (2026-11-15)

Se clonó `origin/dev` en `ae44fd722a6ba43d027f33f53d2cabb1919fbd37` con
árbol limpio. Antes de iniciar Docker se verificó un proyecto Compose único,
puertos loopback 59402–59404 libres, tags de imagen exclusivos, ocho volúmenes
sin colisión y PostgreSQL de producto separado del de Airflow. Los datos se
montaron desde el repositorio original en solo lectura y se excluyeron del
clon/contextos de build.

El comando de arranque del README (`docker compose up --build -d`) funcionó:
`product-init` creó el experimento y el modelo champion v1 automáticamente;
`/health` y `/modelo` respondieron 200. Tras `docker compose stop` y `up -d`,
el bootstrap reutilizó v1, health/modelo siguieron disponibles y el reenvío
idéntico de una observación devolvió 0 registros. No se ejecutó inicialización
manual. Se usó una observación sintética, sin registrar su valor en esta
evidencia.

Desviaciones del README: se fijaron `COMPOSE_PROJECT_NAME`, `COMPOSE_FILE`,
tags temporales de imagen y puertos exclusivos; el bucle de health consultó
59402 en vez de 8000. `.env.example` se completó con credenciales temporales
locales y `DATA_DIR` apuntó al directorio de datos externo mediante bind de
solo lectura. No se cambió el Compose principal. El entorno temporal quedó
detenido con `stop`; sus volúmenes se conservaron. El inventario del entorno
principal (15 runs MLflow, alias champion y versiones) quedó igual. Evidencia:
`evidencias/r26_clone_origin_dev.json`.

R26 queda verificado con estas adaptaciones explícitas; no requirió pasos
adicionales de inicialización.
