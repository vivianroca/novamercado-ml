"""Aceptación real opt-in en un proyecto Compose nuevo; conserva todos los volúmenes."""
import argparse
import base64
import csv
from datetime import date, timedelta, datetime, timezone
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time

import httpx

RAIZ = Path(__file__).resolve().parents[1]
MODELO = 'novamercado-histgradientboosting'


def puerto_libre():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def inventario(uri):
    from mlflow import MlflowClient
    c = MlflowClient(tracking_uri=uri, registry_uri=uri)
    e = c.get_experiment_by_name('NovaMercado')
    ids = []
    if e:
        token = None
        while True:
            pagina = c.search_runs([e.experiment_id], max_results=1000, page_token=token)
            ids.extend(r.info.run_id for r in pagina)
            token = pagina.token
            if not token:
                break
    modelos = []
    token = None
    while True:
        pagina = c.search_registered_models(max_results=100, page_token=token)
        for m in pagina:
            versiones = list(c.search_model_versions(f"name='{m.name}'", max_results=1000))
            modelos.append({'nombre': m.name, 'aliases': dict(m.aliases),
                            'versiones': sorted([v.version, v.run_id] for v in versiones)})
        token = pagina.token
        if not token:
            break
    return {'run_ids': sorted(ids), 'modelos': sorted(modelos, key=lambda m: m['nombre'])}


def validar_config(config, proyecto):
    if not proyecto.startswith('novamercado-e2e-') or config['name'] != proyecto:
        raise ValueError('Se requiere proyecto e2e nuevo')
    for tipo in ('volumes', 'networks'):
        for valor in config.get(tipo, {}).values():
            if valor.get('external') or not valor.get('name', '').startswith(proyecto + '_'):
                raise ValueError('Recurso externo o compartido bloqueado')
    for servicio in config['services'].values():
        esperados = {'MLFLOW_TRACKING_URI': 'http://mlflow:5000',
                     'PRODUCT_DB_HOST': 'product-db', 'AIRFLOW_BASE_URL': 'http://airflow-apiserver:8080'}
        for variable, valor in esperados.items():
            if variable in servicio.get('environment', {}) and servicio['environment'][variable] != valor:
                raise ValueError('Dependencia fuera del proyecto aislado bloqueada')
        if servicio.get('network_mode') or servicio.get('privileged'):
            raise ValueError('Acceso global de red/host bloqueado')
        if servicio.get('build') and not servicio.get('image', '').startswith(proyecto+'-'):
            raise ValueError('Build sobre etiqueta principal bloqueado')
        if servicio.get('container_name'):
            raise ValueError('Nombre de contenedor global bloqueado')
        for montaje in servicio.get('volumes', []):
            if montaje['type'] == 'bind' and not montaje.get('read_only'):
                raise ValueError('Bind modificable bloqueado')
        for puerto in servicio.get('ports', []):
            if int(puerto['published']) in (8000, 8080, 5001):
                raise ValueError('Puerto principal bloqueado')


def esperar_json(url, aceptar, limite, *, intervalo=2):
    ultimo = None
    while time.monotonic() < limite:
        try:
            r = httpx.get(url, timeout=12)
            ultimo = f'HTTP {r.status_code}'
            if r.status_code == 200 and aceptar(r.json()):
                return r.json()
        except (httpx.HTTPError, ValueError) as error:
            ultimo = type(error).__name__
        time.sleep(min(intervalo, max(0, limite-time.monotonic())))
    raise TimeoutError(f'Plazo agotado esperando {url}: {ultimo}')


def ejecutar(data_dir, salida, *, resiliencia=False):
    proyecto = 'novamercado-e2e-' + secrets.token_hex(5)
    trabajo = RAIZ / '.e2e' / proyecto
    trabajo.mkdir(parents=True, mode=0o700)
    if resiliencia:
        if __package__:
            from .escenario_resiliencia import generar_escenario, simular_dias
        else:
            from escenario_resiliencia import generar_escenario, simular_dias
        data_dir = generar_escenario(trabajo/'datos')
    env_path = trabajo / '.env' 
    puertos = set()
    while len(puertos) < 3:
        puertos.add(puerto_libre())
    api, mlflow, airflow = sorted(puertos)
    variables = {'PRODUCT_DB': 'producto', 'PRODUCT_DB_USER': 'producto',
        'PRODUCT_DB_PASSWORD': secrets.token_hex(24), 'AIRFLOW_DB': 'airflow',
        'AIRFLOW_DB_USER': 'airflow', 'AIRFLOW_DB_PASSWORD': secrets.token_hex(24),
        'AIRFLOW_ADMIN_USER': 'e2e', 'AIRFLOW_ADMIN_PASSWORD': secrets.token_hex(24),
        'AIRFLOW_FERNET_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        'AIRFLOW_SECRET_KEY': secrets.token_hex(32), 'AIRFLOW_UID': '50000',
        'DATA_DIR': str(data_dir.resolve()), 'MODEL_NAME': MODELO,
        'API_PORT': str(api), 'MLFLOW_PORT': str(mlflow), 'AIRFLOW_PORT': str(airflow)}
    env_path.write_text(''.join(f'{k}={v}\n' for k, v in variables.items()))
    env_path.chmod(0o600)
    override = trabajo / 'compose.json'
    override.write_text(json.dumps({'services': {
        **{s: {'image': f'{proyecto}-api:1.0.0'} for s in ('api', 'product-init')},
        **{s: {'image': f'{proyecto}-airflow:3.3.2'} for s in
           ('airflow-init', 'airflow-apiserver', 'airflow-scheduler', 'airflow-dag-processor')}
    }}))
    # No heredar credenciales, puertos, perfiles ni proyecto del shell del usuario.
    entorno = {k: v for k, v in os.environ.items() if not
        (k.startswith(('COMPOSE_', 'PRODUCT_DB', 'AIRFLOW_', 'MLFLOW_', 'MODEL_')) or
         k in variables)}
    entorno['MLFLOW_DISABLE_AGENT_HINT'] = '1'
    comando = ['docker', 'compose', '--project-name', proyecto, '--env-file', str(env_path),
               '-f', str(RAIZ/'compose.yaml'), '-f', str(override)]
    def compose(*args, timeout=600):
        with (trabajo/'compose.log').open('a') as log:
            subprocess.run([*comando, *args], cwd=RAIZ, env=entorno, check=True,
                           timeout=timeout, stdout=log, stderr=log)
    config = json.loads(subprocess.check_output([*comando, 'config', '--format', 'json'], env=entorno))
    validar_config(config, proyecto)
    existentes = subprocess.check_output(['docker', 'volume', 'ls', '--format', '{{.Name}}'], text=True).splitlines()
    if any(v.startswith(proyecto+'_') for v in existentes):
        raise ValueError('Volúmenes e2e deben ser nuevos')
    principal = inventario('http://127.0.0.1:5001')
    reporte = {'proyecto': proyecto, 'puertos': {'api': api, 'mlflow': mlflow, 'airflow': airflow},
               'principal_antes': principal, 'etapas': {}, 'estado': 'en_curso'}
    salida.parent.mkdir(parents=True, exist_ok=True)
    def guardar():
        salida.write_text(json.dumps(reporte, ensure_ascii=False, indent=2)+'\n')
    def etapa(nombre):
        print(nombre, flush=True)
        reporte['etapa_actual'] = nombre
        guardar()
    iniciado = False
    try:
        etapa('Construcción de imágenes aisladas (excluida del cronómetro)')
        compose('build', 'product-init', 'airflow-init', timeout=1200)
        etapa('Registry vacío y primer arranque')
        inicio = time.monotonic()
        iniciado = True
        compose('up', '-d', '--no-build', 'mlflow')
        esperar_json(f'http://127.0.0.1:{mlflow}/api/2.0/mlflow/experiments/search?max_results=1',
                     lambda x: 'experiments' in x, inicio+600)
        vacio = inventario(f'http://127.0.0.1:{mlflow}')
        assert not vacio['run_ids'] and not vacio['modelos'], 'Registry no vacío'
        compose('up', '-d', '--no-build', timeout=max(1, 600-(time.monotonic()-inicio)))
        base = f'http://127.0.0.1:{api}'
        esperar_json(base+'/health', lambda x: x.get('estado') == 'ok', inicio+600)
        modelo = httpx.get(base+'/modelo').json()
        reporte['etapas']['bootstrap'] = {'segundos': time.monotonic()-inicio,
            'limite': 600, 'registry_inicial': vacio, 'modelo': modelo}
        guardar()
        etapa('Observaciones idempotentes y predicción real')
        if resiliencia:
            etapa('Simulación diaria: 140 días, errores inéditos y reentrenamientos periódicos')
            eventos = {}
            def reentrenar_periodo(dias):
                version_previa = httpx.get(base+'/modelo', timeout=20).json()['version']
                inicio_periodo = time.monotonic()
                inicio_resp = httpx.post(base+'/admin/reentrenar', timeout=30)
                assert inicio_resp.status_code == 202, inicio_resp.text
                id_periodo = inicio_resp.json()['id']
                resultado = esperar_json(base+'/admin/reentrenar/'+id_periodo,
                    lambda x: x.get('estado') in ('exitoso', 'fallido'),
                    inicio_periodo+600)
                assert resultado['estado'] == 'exitoso', resultado
                inicio_refresh = time.monotonic()
                modelo_actual = esperar_json(base+'/modelo',
                    lambda x: x.get('version') == resultado['version'], inicio_refresh+120)
                registro = {'dia_simulado': dias, 'id': id_periodo,
                    'segundos': time.monotonic()-inicio_periodo, 'resultado': resultado,
                    'segundos_hasta_version_servida': time.monotonic()-inicio_refresh,
                    'limite_refresco': 120, 'modelo_servido': modelo_actual}
                if dias in (70, 105):
                    servicios = ['product-db', 'api'] if dias == 70 else ['mlflow', 'api']
                    inicio_reinicio = time.monotonic()
                    compose('restart', *servicios)
                    esperar_json(base+'/health', lambda x: x.get('estado') == 'ok',
                                 time.monotonic()+120, intervalo=.5)
                    despues = httpx.get(base+'/modelo', timeout=20).json()
                    assert despues['version'] == resultado['version'], (despues, resultado)
                    registro['reinicio'] = {'servicios': servicios,
                        'segundos_hasta_health_ok': time.monotonic()-inicio_reinicio,
                        'modelo_despues': despues}
                return registro
            prediccion, cuerpo = simular_dias(base, httpx, al_periodo=reentrenar_periodo,
                inyectar_errores=True, cada_reentrenamiento=35, eventos=eventos)
            reporte['escenario'] = {'sintetico': True, 'dias': 140,
                'orden': 'predicción D, observación D antes de predicción D+1',
                'cambio_demanda': {'indice': 'tras 420 días históricos', 'ventas': '120 → 320 + calendario/promoción'},
                'errores_no_catalogados': ['familia desconocida', 'venta fraccionaria', 'duplicado contradictorio'],
                'periodicidad_reentrenamiento_dias': 35,
                'politica_promocion_modificada': False,
                'eventos': eventos}
        else:
            with (data_dir/'historico_ventas.csv').open() as f:
                filas = list(csv.DictReader(f))
            ultima = max(filas, key=lambda f: f['fecha'])
            dia = date.fromisoformat(ultima['fecha'])+timedelta(days=1)
            cuerpo = {'tienda_id': int(ultima['tienda_id']), 'fecha': str(dia),
                      'ventas': [{'familia_id': ultima['familia_id'], 'ventas': int(ultima['ventas'])}]}
            for esperados in (1, 0):
                r = httpx.post(base+'/v1/observaciones', json=cuerpo)
                assert r.status_code == 200 and r.json()['registros_guardados'] == esperados, r.text
            prediccion = {'tienda_id': cuerpo['tienda_id'], 'fecha': str(dia+timedelta(days=1)),
                'familias': [{'familia_id': ultima['familia_id'], 'en_promocion': int(ultima['en_promocion'])}]}
        r = httpx.post(base+'/v1/prediccion', json=prediccion, timeout=30)
        assert r.status_code == 200, r.text
        reporte['etapas']['operacion'] = {'observaciones': [1, 0], 'prediccion': r.json()}
        etapa('Reentrenamiento real mediante FastAPI y Airflow aislados')
        def identidad_api():
            identificador = subprocess.check_output([*comando, 'ps', '-q', 'api'], env=entorno, text=True).strip()
            valor = json.loads(subprocess.check_output(['docker','inspect','--format','{{json .State}}',identificador],text=True))
            return {'id':identificador,'iniciada_en':valor['StartedAt']}
        identidad_inicial = identidad_api()
        version_anterior = httpx.get(base+'/modelo').json()['version']
        inicio = time.monotonic()
        r = httpx.post(base+'/admin/reentrenar', timeout=30)
        assert r.status_code == 202, r.text
        identificador = r.json()['id']
        terminal = esperar_json(base+'/admin/reentrenar/'+identificador,
            lambda x: x.get('estado') in ('exitoso', 'fallido'), inicio+600)
        reporte['etapas']['reentrenamiento'] = {'id': identificador,
            'segundos': time.monotonic()-inicio, 'limite': 600, 'resultado': terminal}
        guardar()
        assert terminal['estado'] == 'exitoso', terminal
        if resiliencia:
            assert terminal['promovido'] is True and terminal['version'] != version_anterior, terminal
        inicio = time.monotonic()
        esperar_json(base+'/modelo', lambda x: x['version'] == terminal['version'], inicio+120)
        # Medir también desde el fin confirmado del DagRun, no solo desde el polling.
        auth = httpx.post(f'http://127.0.0.1:{airflow}/auth/token',
            json={'username':variables['AIRFLOW_ADMIN_USER'],'password':variables['AIRFLOW_ADMIN_PASSWORD']})
        auth.raise_for_status()
        run = httpx.get(f'http://127.0.0.1:{airflow}/api/v2/dags/novamercado_reentrenamiento/dagRuns/{identificador}',
            headers={'Authorization':'Bearer '+auth.json()['access_token']})
        run.raise_for_status()
        fin_dag = datetime.fromisoformat(run.json()['end_date'].replace('Z','+00:00'))
        demora = max(0, (datetime.now(timezone.utc)-fin_dag).total_seconds())
        assert demora <= 120
        assert identidad_api() == identidad_inicial, 'API reiniciada durante promoción'
        r = httpx.post(base+'/v1/prediccion',json=prediccion,timeout=30)
        assert r.status_code == 200 and r.json()['version_modelo'] == terminal['version'], r.text
        reporte['etapas']['actualizacion_servida'] = {'segundos_desde_fin_dag':demora,
            'segundos_desde_consulta_terminal':time.monotonic()-inicio,'limite':120,
            'fin_dag_utc':fin_dag.isoformat(),'observado_utc':datetime.now(timezone.utc).isoformat(),
            'promovido':terminal['promovido'],'version_anterior':version_anterior,
            'version':terminal['version'],'api_sin_reinicio':True,'prediccion':r.json()}
        guardar()
        if resiliencia:
            etapa('Caída de MLflow aislado; predicción continúa')
            esperado = r.json()
            inicio = time.monotonic()
            compose('stop','mlflow',timeout=45)
            degradado = esperar_json(base+'/health',lambda x:x.get('estado')=='degradado',inicio+60,intervalo=.5)
            caida = time.monotonic()-inicio
            assert caida < 60, 'Salud degradada fuera de plazo'
            assert 'mlflow' in degradado['motivo'].lower()
            predicciones = []
            # Cubrir al menos un refresco fallido (intervalo de producción 30 s).
            while True:
                r = httpx.post(base+'/v1/prediccion',json=prediccion,timeout=20)
                assert r.status_code == 200 and r.json() == esperado,r.text
                predicciones.append({'segundos_desde_caida':time.monotonic()-inicio,'version':r.json()['version_modelo']})
                salud = httpx.get(base+'/health',timeout=12).json()
                if 'actualización del champion' in salud.get('motivo',''):
                    break
                assert time.monotonic()-inicio < 60,'No se observó refresco fallido'
                time.sleep(2)
            etapa('Recuperación de MLflow aislado')
            regreso = time.monotonic()
            compose('start','mlflow',timeout=45)
            esperar_json(base+'/health',lambda x:x.get('estado')=='ok',regreso+120,intervalo=.5)
            recuperacion = time.monotonic()-regreso
            assert recuperacion < 120, 'Recuperación fuera de plazo'
            r = httpx.post(base+'/v1/prediccion',json=prediccion,timeout=20)
            assert r.status_code==200 and r.json()==esperado,r.text
            assert identidad_api()==identidad_inicial,'API reiniciada para recuperar MLflow'
            reporte['etapas']['mlflow_resiliencia']={'degradado_segundos':caida,'limite_caida':60,
                'ok_segundos_desde_start':recuperacion,'limite_retorno':120,
                'predicciones_durante_caida':predicciones,'modelo_y_prediccion_conservados':True,
                'api_sin_reinicio':True}
            guardar()
        etapa('Reinicio y persistencia sin duplicar bootstrap')
        antes = inventario(f'http://127.0.0.1:{mlflow}')
        compose('restart', 'product-db', 'mlflow', 'api')
        esperar_json(base+'/health', lambda x: x.get('estado') == 'ok', time.monotonic()+120)
        compose('run', '--rm', '--no-deps', 'product-init', 'python', '-m', 'app.bootstrap')
        despues = inventario(f'http://127.0.0.1:{mlflow}')
        assert antes == despues, 'Bootstrap repetido tras reinicio'
        r = httpx.post(base+'/v1/observaciones', json=cuerpo)
        assert r.status_code == 200 and r.json()['registros_guardados'] == 0, r.text
        reporte['aislado_final'] = despues
        reporte['etapas']['persistencia'] = {'registry_identico': True, 'reenvio': 0}
        reporte['estado'] = 'verificado'
    except Exception as error:
        reporte['estado'] = 'fallido'
        reporte['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        try:
            if iniciado:
                try:
                    compose('logs', '--no-color', timeout=30)
                finally:
                    compose('stop', timeout=120)  # No down, rm -v ni volume rm.
        finally:
            reporte['principal_despues'] = inventario('http://127.0.0.1:5001')
            reporte['principal_intacto'] = reporte['principal_despues'] == principal
            if not reporte['principal_intacto']:
                reporte['estado'] = 'fallido'
                reporte['error'] = 'Cambió el inventario principal; revisar evidencia'
            guardar()
            if not reporte['principal_intacto']:
                raise RuntimeError(reporte['error'])
    print(json.dumps({'estado': reporte['estado'], 'evidencia': str(salida)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ejecutar', action='store_true', help='Autoriza build y entrenamiento reales SOLO aislados')
    parser.add_argument('--resiliencia', action='store_true', help='Cambio de demanda sintético, promoción obligatoria y caída/retorno MLflow')
    parser.add_argument('--data-dir', type=Path, default=RAIZ/'data')
    parser.add_argument('--salida', type=Path)
    args = parser.parse_args()
    if not args.ejecutar:
        parser.error('Usar --ejecutar para la prueba integral opt-in')
    salida = args.salida or RAIZ/'evidencias'/('fase7_resiliencia.json' if args.resiliencia else 'fase7_integral.json')
    ejecutar(args.data_dir, salida, resiliencia=args.resiliencia)
