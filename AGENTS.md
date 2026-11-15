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

Estado: Fase 3.1, esquemas, normalización, dos endpoints POST y persistencia
PostgreSQL del producto. Sin modelo configurado se responde 503. Observaciones
idempotentes, solicitudes/calidad y predicciones versionadas transaccionales.
Sin ML, DAG ni bootstrap de negocio. Integración DB con `TEST_PRODUCT_DB_DSN`
contra servidor exclusivo de pruebas; crea y elimina una base temporal.
Pruebas: `.venv/bin/python -m pytest -q` (Python 3.12).

Fase 4.1: baseline semanal en `ml/`, evaluación temporal diaria y costos. Aún no
conectado a la API; sin MLflow ni modelo avanzado. Comando reproducible en README.

Tracking del baseline implementado en `ml/tracking.py`, experimento único
`NovaMercado`, usando servicio Compose `mlflow`. Registra reporte existente,
sin entrenar ni promover. No hay modelo ejecutable en Registry ni alias vigente.

MLflow servidor/cliente fijados a 3.17.2. Backup de la migración 2.22.0 en
`.backups/` (ignorado); conservar metadata, artefactos y runs existentes.
Pruebas de compatibilidad aisladas en `tests/test_mlflow_compatibilidad.py`.

HGB global implementado en `ml/features.py`, `ml/histgradient.py` y
`ml/entrenamiento.py`. Ajuste/calibración estrictamente anteriores a validación;
calendario y promoción de D son conocidos, rezagos solo usan fechas < D.
Modelo pyfunc registrado en NovaMercado sin alias/promoción, no integrado a API.

Política champion implementada en `ml/promocion.py`: ahorro mínimo 1%, guardas
técnicas/por familia, comparación homogénea y dos artefactos por evaluación.
Entrenamiento la invoca tras FINISHED. Champion no implica serving integrado.
Un único escritor de promociones; sin Airflow ni reentrenamiento automático.

Pytest nunca debe escribir en el tracking/Registry del producto. `tests/conftest.py`
configura stores temporales y bloquea clientes externos. Las pruebas HTTP usan un
servidor local propio con datos/modelos sintéticos; no usar IDs, modelos, backups
ni URLs del servicio principal como fixtures. Conservar runs y modelos existentes.

Serving real implementado en `app/servicios/prediccion.py`: singleton por app,
champion con snapshot modelo/versión y refresco cada 30s; conserva cargado ante
caída MLflow. Features causales de CSV + observaciones PostgreSQL (DB prevalece),
sin usar D/futuro ni fechas <= corte de calibración. No hay Airflow ni reentrenamiento.

Fase 5: DAG manual Airflow 3.3.2 en `airflow/dags/reentrenamiento.py`, tres tareas:
entrenar/evaluar, decidir champion y finalizar resultado. `ml/reentrenamiento.py` reconcilia CSV + DB del
producto; promoción reutiliza política y reevalúa champion en los mismos casos.
Endpoints administrativos implementados en `app/api/administracion.py` mediante
adaptador REST v2 sustituible. Pytest bloquea Airflow real salvo MockTransport.
Ante prohibición de entrenar usar `pytest tests -q -k 'not dag_airflow_real'`:
excluye dos pruebas que ejecutan entrenamientos. SDK real se prueba con `.venv-airflow` separado
(airflow/requirements-test.txt), metastore temporal y MLflow aislado de pytest.


Modelo y salud implementados en `app/api/estado.py` y `app/servicios/salud.py`.
Lifespan inicia carga/refresco en segundo plano; intervalo máximo 30 s. Modelo
reportado es el snapshot servido; no sustituirlo por una consulta al alias.
Sin modelo health 503; dependencias caídas con modelo cargado health 200 degradado.
Sondas de solo lectura con timeouts; nunca ejecutar DAGs desde health.
Tests de estado simulan fuentes y red; uno espera el intervalo real de 30 s.


Fase 6: `app/bootstrap.py` y servicio Compose `product-init` aplican esquema y
reutilizan champion READY; solo entrenan inicialmente cuando falta. Checkpoint y
lock en model-cache; nunca confundir error de Registry con modelo inexistente.
Pruebas bootstrap sustituyen entrenamiento/promoción. Para verificación operativa
sin entrenar, usar `python -m app.bootstrap --solo-reutilizar`. No ejecutar el
bootstrap normal contra Registry vacío cuando se prohíben entrenamientos reales.
