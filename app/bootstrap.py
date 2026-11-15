"""Inicializador idempotente del producto; nunca dispara un DAG de Airflow."""
import argparse
from datetime import timedelta
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile

from mlflow.exceptions import MlflowException

from app.db.migrar import aplicar_esquema
from ml.datos import cargar_datos
from ml.features import Contexto
from ml.tracking import INSUMOS, sha256


ARCHIVOS = (*INSUMOS, 'feriados.csv')


def champion(cliente, nombre):
    try:
        registrado = cliente.get_registered_model(nombre)
    except MlflowException as error:
        if error.error_code == 'RESOURCE_DOES_NOT_EXIST':
            return None
        raise  # Una caída del Registry nunca significa "modelo inexistente".
    version = registrado.aliases.get('champion')
    if version is None:
        return None
    modelo = cliente.get_model_version(nombre, str(version))
    if modelo.status != 'READY':
        raise RuntimeError('Champion existente no está READY; no entrenar otro')
    return str(version)


def inicializar(data_dir, tracking_uri, nombre, estado_dir, *, cliente,
                migrar=aplicar_esquema, entrenar=None, promover=None, solo_reutilizar=False):
    estado_dir = Path(estado_dir)
    estado_dir.mkdir(parents=True, exist_ok=True)
    clave = hashlib.sha256(f'{tracking_uri}/{nombre}'.encode()).hexdigest()[:20]
    with (estado_dir / f'bootstrap-{clave}.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        migrar()  # También funciona sobre volúmenes PostgreSQL preexistentes.
        version = champion(cliente, nombre)
        if version:
            return {'estado': 'reutilizado', 'nombre': nombre, 'version': version}
        if solo_reutilizar:
            raise RuntimeError('No hay champion; entrenamiento bloqueado por --solo-reutilizar')
        # Cargar y validar los archivos publicados, sin convertirlos en observaciones.
        historial, _ = cargar_datos(data_dir)
        Contexto.cargar(data_dir)
        hashes = {n: sha256(Path(data_dir) / n) for n in ARCHIVOS}
        reporte_path = estado_dir / f'bootstrap-{clave}.json'
        if reporte_path.exists():
            reporte = json.loads(reporte_path.read_text())
            if reporte['sha256_insumos'] != hashes:
                raise RuntimeError('Insumos cambiaron durante bootstrap incompleto; revisar candidato existente')
        else:
            if entrenar is None:
                from ml.entrenamiento import entrenar_y_registrar
                entrenar = entrenar_y_registrar
            fin = max(v.fecha for v in historial)
            # Guardar checkpoint durable antes de intentar promoción. Al reiniciar,
            # se retoma ese candidato en lugar de volver a ajustarlo.
            with tempfile.TemporaryDirectory(dir=estado_dir) as temporal:
                salida = Path(temporal) / 'reporte.json'
                reporte = entrenar(data_dir, fin - timedelta(days=55), fin, tracking_uri, salida,
                                   promover=False, nombre_modelo=nombre)
                salida.write_text(json.dumps(reporte, allow_nan=False))
                os.replace(salida, reporte_path)
        # Otro escritor pudo publicar durante el entrenamiento: conservarlo.
        version = champion(cliente, nombre)
        if version:
            return {'estado': 'reutilizado', 'nombre': nombre, 'version': version}
        if promover is None:
            from ml.promocion import evaluar_champion
            promover = evaluar_champion
        decision = promover(cliente, nombre, reporte['mlflow']['version'])
        version = champion(cliente, nombre)
        if decision['estado'] != 'exitoso' or not version:
            raise RuntimeError('El primer candidato no produjo un champion válido: ' + decision['motivo'])
        return {'estado': 'inicializado', 'nombre': nombre, 'version': version,
                'sha256_insumos': hashes}


def main():
    from mlflow import MlflowClient
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--solo-reutilizar', action='store_true')
    args = parser.parse_args()
    uri = os.environ['MLFLOW_TRACKING_URI']
    resultado = inicializar(os.environ.get('DATA_DIR', 'data'), uri,
        os.environ.get('MODEL_NAME', 'novamercado-histgradientboosting'),
        os.environ.get('MODEL_CACHE_DIR', 'models'),
        cliente=MlflowClient(tracking_uri=uri, registry_uri=uri), solo_reutilizar=args.solo_reutilizar)
    print(json.dumps(resultado))


if __name__ == '__main__':
    main()
