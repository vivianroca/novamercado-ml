# NovaMercado — Laboratorio 2

Referencia: `PLAN_LABORATORIO_2_NOVAMERCADO.md`, contrastado con el PDF.
Trabajar una fase por solicitud. No adelantar lógica de fases posteriores.

- Contrato del anexo: conservar rutas, campos y códigos HTTP.
- Separar endpoints, esquemas, limpieza, persistencia y ML.
- Insumos disponibles en `data/`, ignorados por Git; no versionarlos ni incluirlos en imágenes.
- Fechas simuladas: no validar fechas contra el reloj del sistema.
- Evitar fuga temporal; observaciones anteriores a la fecha pronosticada.
- PostgreSQL del producto separado del metastore de Airflow.
- Servicio Compose de MLflow llamado exactamente `mlflow`.
- No afirmar funcionamiento sin pruebas. Actualizar documentación y matriz con evidencia.
- No construir ni arrancar contenedores salvo autorización del usuario.

Estado: Fase 1, esqueleto. Sin endpoints, modelo, DAG ni bootstrap de negocio.
