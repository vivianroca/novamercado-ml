"""Bootstrap con entrenamiento/Registry sustituidos; nunca entrena modelos reales."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from types import SimpleNamespace

from mlflow.exceptions import MlflowException
from mlflow.protos.databricks_pb2 import ErrorCode, RESOURCE_DOES_NOT_EXIST
import pytest

from app.bootstrap import ARCHIVOS, inicializar
from ml.tracking import sha256


class Cliente:
    def __init__(self, version=None):
        self.version = version
        self.status = 'READY'
        self.error = None

    def get_registered_model(self, nombre):
        if self.error:
            raise MlflowException('Registry inaccesible', error_code=ErrorCode.Value(self.error))
        return SimpleNamespace(aliases={'champion': self.version} if self.version else {})

    def get_model_version(self, nombre, version):
        return SimpleNamespace(status=self.status)


@pytest.fixture
def entorno(tmp_path):
    datos = tmp_path / 'datos'
    datos.mkdir()
    (datos / 'tiendas.csv').write_text('tienda_id,ciudad,tipo,fecha_apertura\n5,Guatemala,express,2024-01-01\n')
    (datos / 'familias.csv').write_text('familia_id,nombre\npan,Pan\n')
    (datos / 'costos.csv').write_text('familia_id,costo_faltante,costo_sobrante\npan,1,2\n')
    (datos / 'feriados.csv').write_text('fecha,nombre,tipo,ambito\n2026-01-01,Feriado,feriado,nacional\n')
    filas = ['fecha,tienda_id,familia_id,ventas,en_promocion']
    filas += [f'{date(2025, 10, 1)+timedelta(days=i)},5,pan,10,0' for i in range(150)]
    (datos / 'historico_ventas.csv').write_text('\n'.join(filas)+'\n')
    cliente, llamadas = Cliente(), []
    def entrenar(data_dir, inicio, fin, uri, salida, **opciones):
        llamadas.append(('entrenar', inicio, fin, opciones))
        return {'mlflow': {'version': '3'}, 'sha256_insumos': {n: sha256(datos/n) for n in ARCHIVOS}}
    def promover(c, nombre, version):
        llamadas.append(('promover', version))
        c.version = str(version)
        return {'estado': 'exitoso', 'version': str(version)}
    args = dict(data_dir=datos, tracking_uri='http://mlflow.test', nombre='prueba',
        estado_dir=tmp_path/'estado', cliente=cliente, migrar=lambda: llamadas.append(('migrar',)),
        entrenar=entrenar, promover=promover)
    return args, llamadas, cliente


def test_primera_carga_y_reinicio_no_repiten_entrenamiento(entorno):
    args, llamadas, cliente = entorno
    assert inicializar(**args)['estado'] == 'inicializado'
    segundo = inicializar(**{**args, 'cliente': Cliente(cliente.version)})
    assert segundo == {'estado': 'reutilizado', 'nombre': 'prueba', 'version': '3'}
    assert [l[0] for l in llamadas].count('entrenar') == 1
    entrenamiento = next(l for l in llamadas if l[0] == 'entrenar')
    assert entrenamiento[2] - entrenamiento[1] == timedelta(days=55)
    assert entrenamiento[3]['promover'] is False


def test_champion_existente_no_carga_datos_ni_entrena(entorno):
    args, llamadas, cliente = entorno
    cliente.version = '9'
    args['data_dir'] = '/datos/que/no/existen'
    assert inicializar(**args)['version'] == '9'
    assert llamadas == [('migrar',)]


@pytest.mark.parametrize('codigo', ['INTERNAL_ERROR', 'PERMISSION_DENIED'])
def test_registry_caido_no_se_interpreta_como_vacio(entorno, codigo):
    args, llamadas, cliente = entorno
    cliente.error = codigo
    with pytest.raises(MlflowException): inicializar(**args)
    assert llamadas == [('migrar',)]


def test_modelo_ausente_permite_inicializacion(entorno):
    args, _, cliente = entorno
    original = cliente.get_registered_model
    primero = True
    def consultar(nombre):
        nonlocal primero
        if primero:
            primero = False
            raise MlflowException('Ausente', error_code=RESOURCE_DOES_NOT_EXIST)
        return original(nombre)
    cliente.get_registered_model = consultar
    assert inicializar(**args)['version'] == '3'


def test_no_ready_conserva_y_no_entrena(entorno):
    args, llamadas, cliente = entorno
    cliente.version, cliente.status = '9', 'FAILED_REGISTRATION'
    with pytest.raises(RuntimeError, match='READY'): inicializar(**args)
    assert llamadas == [('migrar',)]


def test_modo_operativo_no_entrena_si_no_existe_champion(entorno):
    args, llamadas, _ = entorno
    with pytest.raises(RuntimeError, match='bloqueado'):
        inicializar(**args, solo_reutilizar=True)
    assert llamadas == [('migrar',)]


def test_fallo_promocion_retoma_checkpoint_sin_entrenar(entorno):
    args, llamadas, _ = entorno
    def fallar(*args): raise ConnectionError('Sin Registry')
    with pytest.raises(ConnectionError): inicializar(**{**args, 'promover': fallar})
    assert inicializar(**args)['version'] == '3'
    assert [l[0] for l in llamadas].count('entrenar') == 1


def test_cambio_datos_tras_fallo_requiere_revision(entorno):
    args, llamadas, _ = entorno
    def fallar(*args): raise ConnectionError()
    with pytest.raises(ConnectionError): inicializar(**{**args, 'promover': fallar})
    with (args['data_dir']/'historico_ventas.csv').open('a') as archivo:
        archivo.write('2027-01-01,5,pan,20,0\n')
    with pytest.raises(RuntimeError, match='Insumos cambiaron'): inicializar(**args)
    assert [l[0] for l in llamadas].count('entrenar') == 1


def test_inicializadores_concurrentes_serializados(entorno):
    args, llamadas, _ = entorno
    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(lambda _: inicializar(**args), range(2)))
    assert {r['estado'] for r in resultados} == {'inicializado', 'reutilizado'}
    assert [l[0] for l in llamadas].count('entrenar') == 1


def test_datos_invalidos_no_entrenan(entorno):
    args, llamadas, _ = entorno
    (args['data_dir']/'costos.csv').write_text('familia_id,costo_faltante,costo_sobrante\notro,1,2\n')
    with pytest.raises(ValueError): inicializar(**args)
    assert llamadas == [('migrar',)]


def test_primer_candidato_rechazado_no_finge_modelo(entorno):
    args, _, _ = entorno
    def rechazar(*args): return {'estado': 'exitoso', 'motivo': 'No mejora costo'}
    with pytest.raises(RuntimeError, match='No mejora costo'):
        inicializar(**{**args, 'promover': rechazar})
