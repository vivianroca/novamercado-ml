# NovaMercado — pronóstico de ventas

Servicio FastAPI para pronósticos diarios por tienda y familia. Persiste solicitudes, resultados y observaciones en PostgreSQL; sirve un modelo `champion` de MLflow y permite reentrenar mediante Airflow. El contrato se contrastó con `Laboratorio_2_PD_26_c.pdf`.

## Arranque desde cero

1. Instala Docker Compose y coloca en `data/` los archivos publicados por el curso: `tiendas.csv`, `familias.csv`, `historico_ventas.csv`, `feriados.csv`, `costos.csv`, `catalogo_errores.md` y `ejemplos/`. La ruta puede cambiarse con `DATA_DIR`. Los datos se montan en solo lectura y están ignorados por Git.
2. Prepara el entorno:

   ```sh
   cp .env.example .env
   ```

   Sustituye todos los marcadores. Genera una clave Fernet válida, por ejemplo con `cryptography.fernet.Fernet.generate_key()`. Usa claves y contraseñas propias; `.env` está excluido de Git y de la imagen.

3. Arranca el producto:

   ```sh
   docker compose up --build -d
   docker compose ps
   ```

   `up -d` inicia los servicios en segundo plano; no significa que la API esté lista. Espera hasta que `/health` devuelva `estado=ok` (hasta 10 minutos, límite del PDF). Este bucle consulta cada 5 segundos y trata una respuesta degradada o una conexión aún no disponible como espera:

   ```sh
   intento=0
   while [ "$intento" -lt 120 ]; do
     estado=$(curl -fsS http://127.0.0.1:8000/health 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("estado", ""))' 2>/dev/null || true)
     if [ "$estado" = ok ]; then
       echo "API lista: /health estado=ok"
       break
     fi
     intento=$((intento + 1))
     sleep 5
   done
   if [ "$estado" != ok ]; then
     docker compose ps
     docker compose logs product-init api mlflow airflow-apiserver airflow-scheduler airflow-dag-processor
     exit 1
   fi
   ```

   La API espera que termine `product-init` y que Airflow esté saludable. Desde Registry vacío, el bootstrap valida los CSV, entrena y registra un primer modelo y aplica la política normal de promoción. En un Registry con `champion` READY reutiliza el modelo. La prueba aislada con Registry vacío llegó a `/health: ok` en 65,16 s; el tiempo depende del equipo y los insumos. Si `/health` responde `degradado`, el servicio respondió pero alguna dependencia aún falla; sigue esperando y, al agotarse el límite, revisa los logs indicados.

   Al detener y volver a levantar, los servicios reutilizan sus volúmenes:

   ```sh
   docker compose stop
   docker compose up -d
   ```

   No uses `down -v` para conservar la base del producto, el Registry, los artefactos, el metastore, la autenticación y la caché del modelo.

## Servicios y configuración

| Servicio | Uso | Acceso local |
|---|---|---|
| `api` | FastAPI, puerto 8000 | `http://127.0.0.1:8000` |
| `product-db` | Solicitudes, predicciones y observaciones | Red interna; volumen `product-db` |
| `mlflow` | Tracking y Model Registry, versión 3.17.2 | `http://127.0.0.1:5001` |
| `airflow-apiserver` | API y UI de Airflow 3.3.2 | `http://127.0.0.1:8080` |
| `airflow-scheduler`, `airflow-dag-processor` | Ejecución y lectura del DAG | Red interna |
| `airflow-db` | Metastore de Airflow | Red interna; separado de `product-db` |
| `product-init`, `airflow-init` | Inicialización de una sola ejecución | No publican puertos |

Las imágenes usan versiones explícitas en `compose.yaml` y los Dockerfiles. Los volúmenes de producto y Airflow son independientes. `DATA_DIR`, puertos, credenciales, modelo y tiempos de refresco se configuran en `.env`; `.env.example` contiene marcadores, no credenciales funcionales.

Compose mantiene dos operaciones administrativas separadas: `airflow-init` migra el metastore y prepara SimpleAuth; `product-init` aplica el esquema de producto y crea un modelo solo cuando falta un champion. Si no hay modelo READY, cambian los hashes de datos durante un bootstrap interrumpido o MLflow está inaccesible, revisa `docker compose logs product-init`. No borres el checkpoint ni los volúmenes para resolverlo sin diagnosticar.

## API

La documentación de FastAPI está habilitada:

- `GET /docs`
- `GET /redoc`
- `GET /openapi.json`

Rutas del contrato:

| Ruta | Resultado |
|---|---|
| `POST /v1/prediccion` | 200 con venta esperada, sugerido entero, versión y calidad; 422 ante entrada inválida; 503 si falta modelo, DB o confirmación persistente. |
| `POST /v1/observaciones` | 200 con `registros_guardados` (nuevos + modificados; reenvío idéntico: 0) y calidad; 422 entrada inválida; 503 si no se confirma el guardado. |
| `POST /admin/reentrenar` | Sin cuerpo. 202 con el ID confirmado por Airflow; 503 si no se puede iniciar. |
| `GET /admin/reentrenar/{id}` | 200 con `en_curso` o estado terminal y `promovido`, `version`, `motivo`; 404 para ID desconocido; 503 para resultado no verificable. |
| `GET /modelo` | 200 con nombre, alias y versión del snapshot servido; 503 sin modelo cargado. |
| `GET /health` | 200 `ok`, 200 `degradado` con motivo, o 503 si no hay modelo. Comprueba API, PostgreSQL, MLflow, Airflow y champion. |

FastAPI carga el champion al arrancar y revisa el alias cada 30 segundos como máximo. Sustituye el snapshot solo tras validar la nueva versión. Si MLflow cae, mantiene las predicciones con el modelo ya cargado. La caída y recuperación se midieron en Compose aislado: health degradado en 1,38 s y de vuelta a `ok` en 29,03 s.

## Modelo, promoción y reentrenamiento

El experimento es `NovaMercado`; el modelo registrado es `novamercado-histgradientboosting`; el alias servido es `champion`. HistGradientBoosting usa variables causales de calendario, tienda, familia, promociones, feriados y rezagos. El costo de inventario sigue la fórmula del PDF: `costo_faltante * max(real - sugerido, 0) + costo_sobrante * max(sugerido - real, 0)`.

La promoción requiere reducir el costo total al menos 1%, sin empeorar MAE/RMSE/WAPE más de 5% ni el costo de una familia más de 10%. Los candidatos se comparan sobre las mismas fechas y casos. Empates, fallos y candidatos rechazados conservan el champion. `DECISIONES.md` describe la normalización, variables, sugeridos, política y limitaciones.

Airflow ejecuta el DAG manual `novamercado_reentrenamiento`, con las tareas `entrenar_y_evaluar`, `decidir_champion` y `finalizar_reentrenamiento`. No tiene cron ni catchup. El snapshot combina el histórico con observaciones del producto; las observaciones prevalecen por clave. La API administrativa dispara el DAG. Evita ejecuciones manuales concurrentes: MLflow tiene un único escritor de alias.

## Pruebas

Instala Python 3.12 y las dependencias:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Suite que no ejecuta los casos DAG con entrenamiento:

```sh
MLFLOW_TRACKING_URI=http://127.0.0.1:59999 .venv/bin/python -m pytest tests -q -k 'not dag_airflow_real'
```

Pytest sustituye las URIs heredadas por tracking/Registry temporales y bloquea el acceso de sus clientes a MLflow externo. La suite no necesita MLflow principal. Sin `TEST_PRODUCT_DB_DSN`, pytest omite los casos que requieren PostgreSQL real.

Para ejecutar pruebas de persistencia, define `TEST_PRODUCT_DB_DSN` contra un servidor PostgreSQL **exclusivo de pruebas**. Las pruebas crean y eliminan bases con nombres aleatorios dentro de ese servidor; no apuntes la variable a una base de producto ni al metastore de Airflow. Para los tests que importan el SDK de Airflow instala el entorno separado:

```sh
python3.12 -m venv .venv-airflow
.venv-airflow/bin/python -m pip install -r airflow/requirements-test.txt
```

Los tests `dag_airflow_real` entrenan modelos sintéticos en stores aislados; ejecutar ese grupo solo cuando se quiera probar dicho trabajo. Resultado focalizado documentado en Fase 8: 177 aprobadas y 2 casos de DAG excluidos; regresión completa documentada: 284 aprobadas. No se ejecutan automáticamente en el arranque del producto.

## Evidencias y aceptación aislada

Evidencias principales en `evidencias/`:

- `comparacion_histgradient.json`: baseline y HGB, métricas globales/por familia y hashes.
- `fase_3_1_postgresql.md`: idempotencia, rollback y persistencia.
- `airflow_fase5.json`, `endpoints_administrativos.json`: DAG/contrato administrativo.
- `fase7_integral.json`: Registry vacío, bootstrap, predicción, DAG y persistencia aislada.
- `fase7_resiliencia.json`, `fase7_promocion_comparacion.csv`, `fase7_promocion_decision.md`: promoción efectiva, refresco sin reinicio y caída/retorno de MLflow.
- `r31_operacion_extendida.json`: 140 días simulados, errores inéditos, reentrenamientos periódicos, reinicios, caída/recuperación y verificación de que el inventario principal quedó intacto.
- `r31_iteracion_fallo_refresco.json`: diagnóstico de una primera corrida del verificador que detectó una aserción prematura de refresco; no es una falla del producto ni cuenta como aceptación completada.
- `auditoria_p1.json`: pruebas y consulta DB de Fase 8.1.
- `respuestas_api.json`: capturas HTTP 200/422 de ambas rutas de negocio; identifica cuáles usan dobles de contrato y cuál proviene de Compose aislado.

El runner integral crea recursos Compose nuevos, ejecuta entrenamiento real y conserva los volúmenes aislados al terminar. No es una prueba unitaria:

```sh
.venv/bin/python scripts/verificar_integral.py --ejecutar
.venv/bin/python scripts/verificar_integral.py --ejecutar --resiliencia
```

El modo resiliencia genera sus propios CSV sintéticos (420 días de historial y 140 días operados), inyecta errores no catalogados, ejecuta reentrenamientos periódicos, reinicia servicios y comprueba caída/retorno de MLflow. Antes de usarlo, verifica Docker y acceso de solo lectura al MLflow local principal en 5001 para comparar su inventario antes/después. Los proyectos y credenciales temporales quedan bajo `.e2e/`, ignorado por Git. El runner detiene los servicios aislados; no elimina sus volúmenes.

## Diagnóstico

```sh
docker compose ps
docker compose logs product-init api
docker compose logs mlflow airflow-apiserver airflow-scheduler airflow-dag-processor
docker compose --env-file .env config --quiet
```

`docker compose config --quiet` comprueba la configuración, no inicia servicios ni demuestra disponibilidad. Si `/health` está degradado, `motivo` identifica la dependencia observada. Si Airflow no muestra el DAG, consulta los logs de `airflow-dag-processor`. Si la API no arranca, revisa primero el resultado de `product-init`, MLflow y PostgreSQL.

## Estado de entrega

La documentación de cumplimiento está en `PLAN_LABORATORIO_2_NOVAMERCADO.md`; las notas de planificación previas están marcadas como históricas y la matriz es la referencia vigente. R31 cuenta con la simulación extendida descrita en `evidencias/r31_operacion_extendida.json`. R26 se verificó desde un clon limpio de `origin/dev`; el aislamiento, bootstrap automático, disponibilidad y persistencia tras reinicio están en `evidencias/r26_clone_origin_dev.json`. Sigue pendiente el tag `entrega-lab2` con verificación del acceso docente al remoto. Las capturas HTTP contractuales están en `evidencias/respuestas_api.json`; las respuestas de predicción con modelo real se identifican por separado. Las pruebas aisladas demuestran los escenarios descritos, no garantizan el rendimiento con hardware distinto ni cambios futuros en GES.
