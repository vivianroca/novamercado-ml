FROM apache/airflow:3.3.2-python3.12
USER root
RUN mkdir -p /opt/novamercado /opt/airflow/work /opt/airflow/auth \
    && chown -R airflow:0 /opt/novamercado /opt/airflow/work /opt/airflow/auth \
    && chmod g+w /opt/airflow/work /opt/airflow/auth
USER airflow
WORKDIR /opt/novamercado
COPY --chown=airflow:0 requirements.txt ./requirements.txt
# ML y Airflow tienen dependencias diferentes: no modificar el entorno del SDK.
RUN python -m venv /opt/novamercado/.venv \
    && /opt/novamercado/.venv/bin/pip install --no-user --no-cache-dir -r requirements.txt
COPY --chown=airflow:0 app ./app
COPY --chown=airflow:0 ml ./ml
COPY --chown=airflow:0 airflow/inicializar_auth.py ./airflow/inicializar_auth.py
COPY --chown=airflow:0 airflow/dags /opt/airflow/dags
ENV NOVAMERCADO_ROOT=/opt/novamercado \
    NOVAMERCADO_PYTHON=/opt/novamercado/.venv/bin/python
