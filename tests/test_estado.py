from datetime import date
from types import SimpleNamespace
import threading
import time

from fastapi.testclient import TestClient
import httpx
import pytest

from app.api.dependencias import obtener_predictor
from app.api.estado import obtener_sondas
from app.main import crear_app
from app.servicios.prediccion import CacheChampion, ModeloCargado, PredictorChampion
from app.servicios.salud import SondasDependencias


class Fuente:
    nombre = "modelo-aislado"
    alias = "champion"

    def __init__(self):
        self.version = "1"
        self.caida = False
        self.invalido = False
        self.bloquear = None

    def consultar(self):
        if self.caida:
            raise ConnectionError("secreto que no debe aparecer")
        return SimpleNamespace(version=self.version)

    def cargar(self, version):
        if self.bloquear:
            assert self.bloquear.wait(3)
        if self.invalido:
            raise ValueError("Inválido")
        return ModeloCargado(object(), version.version, date(2026, 1, 1), {})


class Sondas:
    def __init__(self):
        self.fallos = []

    def comprobar(self):
        return list(self.fallos)


@pytest.fixture
def entorno():
    fuente, sondas = Fuente(), Sondas()
    cache = CacheChampion(fuente, intervalo=0.02)
    predictor = PredictorChampion(cache, None)
    app = crear_app()
    app.state.predictor = predictor
    app.dependency_overrides[obtener_predictor] = lambda: predictor
    app.dependency_overrides[obtener_sondas] = lambda: sondas
    with TestClient(app) as cliente:
        yield cliente, cache, fuente, sondas


def esperar(chequeo, limite=2):
    inicio = time.monotonic()
    while not chequeo():
        assert time.monotonic() - inicio < limite
        time.sleep(.005)
    return time.monotonic() - inicio


def test_sin_modelo_503_y_recupera_sin_predicciones():
    fuente = Fuente()
    fuente.caida = True
    cache = CacheChampion(fuente, intervalo=.02)
    app = crear_app()
    app.state.predictor = PredictorChampion(cache, None)
    app.dependency_overrides[obtener_sondas] = Sondas
    with TestClient(app) as cliente:
        assert cliente.get('/health').status_code == 503
        assert cliente.get('/modelo').status_code == 503
        fuente.caida = False
        esperar(lambda: cache.actual is not None)
        assert cliente.get('/health').json() == {'estado': 'ok'}
        assert cliente.get('/modelo').json() == {'nombre': fuente.nombre, 'alias': 'champion', 'version': '1'}


def test_cambio_champion_periodico_sin_reinicio_y_version_atomica(entorno):
    cliente, cache, fuente, _ = entorno
    cache.obtener()
    assert cliente.get('/modelo').json()['version'] == '1'
    fuente.bloquear = threading.Event()
    fuente.version = '2'
    # Mientras la carga está incompleta se sigue exponiendo el modelo anterior.
    assert cliente.get('/modelo').json()['version'] == '1'
    fuente.bloquear.set()
    transcurrido = esperar(lambda: cliente.get('/modelo').json()['version'] == '2')
    assert transcurrido < 120
    assert cache.obtener().version == '2'


def test_caida_y_retorno_mlflow_tiempos_y_conserva_modelo(entorno):
    cliente, cache, fuente, sondas = entorno
    anterior = cache.obtener()
    fuente.caida, sondas.fallos = True, ['mlflow']
    assert esperar(lambda: cliente.get('/health').json()['estado'] == 'degradado') < 60
    esperar(lambda: cache.ultimo_error is not None)
    assert cache.obtener() is anterior
    assert cliente.get('/modelo').json()['version'] == '1'
    assert 'secreto' not in cliente.get('/health').text
    fuente.caida, sondas.fallos = False, []
    assert esperar(lambda: cliente.get('/health').json()['estado'] == 'ok') < 120


@pytest.mark.parametrize('fallo', ['db', 'mlflow', 'airflow'])
def test_dependencia_fallida_es_200_degradado(entorno, fallo):
    cliente, cache, _, sondas = entorno
    cache.obtener()
    sondas.fallos = [fallo]
    respuesta = cliente.get('/health')
    assert respuesta.status_code == 200
    assert respuesta.json()['estado'] == 'degradado'
    assert fallo in respuesta.json()['motivo']


def test_modelo_incompatible_no_se_publica_y_salud_degrada(entorno):
    cliente, cache, fuente, _ = entorno
    cache.obtener()
    fuente.version, fuente.invalido = '2', True
    esperar(lambda: cache.ultimo_error is not None)
    assert cliente.get('/modelo').json()['version'] == '1'
    assert cliente.get('/health').json()['estado'] == 'degradado'


@pytest.mark.parametrize('intervalo', [0, -1, 31, 120, float('nan'), float('inf')])
def test_intervalo_impide_configuracion_fuera_del_plazo(intervalo):
    with pytest.raises(ValueError):
        CacheChampion(Fuente(), intervalo)


@pytest.mark.parametrize('fallo', [None, 'mlflow', 'scheduler', 'dag_processor', 'metadatabase', 'json'])
def test_sondas_reales_con_http_simulado_y_db_sustituida(monkeypatch, fallo):
    monkeypatch.setenv('MLFLOW_TRACKING_URI', 'http://mlflow.test')
    monkeypatch.setenv('AIRFLOW_BASE_URL', 'http://airflow.test')
    llamadas = []
    def handler(request):
        llamadas.append(request.url.path)
        if request.url.host == 'mlflow.test':
            return httpx.Response(503 if fallo == 'mlflow' else 200)
        if fallo == 'json':
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={c: {'status': 'unhealthy' if fallo == c else 'healthy'}
            for c in ['metadatabase', 'scheduler', 'dag_processor']})
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql): llamadas.append(sql)
        def fetchone(self): return (1,)
    class Conexion(Cursor):
        def cursor(self): return Cursor()
    sondas = SondasDependencias(Conexion, httpx.MockTransport(handler))
    assert sondas.comprobar() == ([] if fallo is None else ['mlflow' if fallo == 'mlflow' else 'airflow'])
    assert 'SELECT 1' in llamadas
    assert '/api/v2/monitor/health' in llamadas


def test_sonda_db_error_sanitizado():
    class Salud(SondasDependencias):
        def db(self): raise RuntimeError('password=secreto')
        def mlflow(self): pass
        def airflow(self): pass
    assert Salud().comprobar() == ['db']


def test_intervalo_por_defecto_actualiza_sin_reiniciar(record_property):
    fuente = Fuente()
    cache = CacheChampion(fuente)  # Intervalo de producción, 30 segundos reales.
    app = crear_app()
    app.state.predictor = PredictorChampion(cache, None)
    with TestClient(app) as cliente:
        esperar(lambda: cache.actual is not None)
        assert cliente.get('/modelo').json()['version'] == '1'
        fuente.version = '2'
        inicio = time.monotonic()
        while cliente.get('/modelo').json()['version'] != '2':
            assert time.monotonic() - inicio < 40
            time.sleep(.05)
        transcurrido = time.monotonic() - inicio
        record_property('actualizacion_champion_segundos', transcurrido)
        assert transcurrido < 120


def test_lifespan_inicia_carga_sin_primera_prediccion():
    fuente = Fuente()
    cache = CacheChampion(fuente)
    app = crear_app()
    app.state.predictor = PredictorChampion(cache, None)
    with TestClient(app):
        esperar(lambda: cache.actual is not None)
        assert cache.actual.version == '1'
    assert cache._stop.is_set()


def test_http_predice_con_nueva_version_y_continua_sin_mlflow():
    import pandas as pd
    from app.api.dependencias import obtener_catalogos, obtener_registro_predicciones
    from app.calidad.normalizacion import Catalogos
    class Modelo:
        def __init__(self, valor): self.valor = valor
        def predict(self, x):
            return pd.DataFrame([{'venta_esperada': self.valor, 'cantidad_sugerida': self.valor}])
    class FuentePredice(Fuente):
        def cargar(self, version):
            return ModeloCargado(Modelo(int(version.version)), version.version, date(2026, 1, 1), {})
    class Variables:
        def matriz(self, solicitud, snapshot): return pd.DataFrame([{}])
    class Registro:
        def guardar_prediccion(self, *args): pass
    fuente, sondas = FuentePredice(), Sondas()
    cache = CacheChampion(fuente, intervalo=.02)
    app = crear_app()
    app.state.predictor = PredictorChampion(cache, Variables())
    app.dependency_overrides[obtener_sondas] = lambda: sondas
    app.dependency_overrides[obtener_catalogos] = lambda: Catalogos(
        frozenset({5}), frozenset({'abarrotes'}), {'abarrotes': 'abarrotes'})
    app.dependency_overrides[obtener_registro_predicciones] = Registro
    entrada = {'tienda_id': 5, 'fecha': '2026-02-01', 'familias': [
        {'familia_id': 'abarrotes', 'en_promocion': 0}]}
    with TestClient(app) as cliente:
        esperar(lambda: cache.actual is not None)
        assert cliente.post('/v1/prediccion', json=entrada).json()['version_modelo'] == '1'
        fuente.version = '2'
        assert esperar(lambda: cliente.get('/modelo').json()['version'] == '2') < 120
        r = cliente.post('/v1/prediccion', json=entrada)
        assert r.status_code == 200 and r.json()['version_modelo'] == '2'
        assert r.json()['predicciones'][0]['venta_esperada'] == 2
        fuente.caida, sondas.fallos = True, ['mlflow']
        esperar(lambda: cache.ultimo_error is not None)
        assert cliente.get('/health').json()['estado'] == 'degradado'
        r = cliente.post('/v1/prediccion', json=entrada)
        assert r.status_code == 200 and r.json()['version_modelo'] == '2'
