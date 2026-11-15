# NovaMercado ML

Fase 3.1: esquemas, normalización, endpoints POST y persistencia PostgreSQL del
producto. Aún no hay modelo, DAG ni entrenamiento inicial.
No es un producto listo para evaluar.

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
para arrancar. No se ha probado ejecución de contenedores en esta fase.

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
El predictor real sigue ausente: predicciones válidas responden 503 con `detail`.
Observaciones usan PostgreSQL del producto; si no está configurado o el guardado
no se puede confirmar, responden 503. No se inventan predicciones ni registros.

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
