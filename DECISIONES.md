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
