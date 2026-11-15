# NovaMercado ML

Fase 1: estructura y configuración. Aún no hay endpoints del contrato, modelo,
DAG de negocio ni carga/entrenamiento inicial. No es un producto listo para evaluar.

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
