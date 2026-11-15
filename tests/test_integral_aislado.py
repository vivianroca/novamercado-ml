"""Guardas del runner; pytest no levanta el stack integral."""
import copy

import pytest

from scripts.verificar_integral import validar_config


@pytest.fixture
def config():
    nombre = 'novamercado-e2e-prueba'
    return {'name': nombre, 'volumes': {'db': {'name': nombre+'_db'}},
            'networks': {'default': {'name': nombre+'_default'}},
            'services': {'api': {'ports': [{'published': '19000'}],
                'volumes': [{'type': 'bind', 'read_only': True}]}}}


def test_config_aislada_permitida(config):
    validar_config(config, config['name'])


@pytest.mark.parametrize('cambio', ['proyecto', 'volumen', 'externo', 'red', 'contenedor', 'bind', 'puerto', 'tracking', 'host', 'imagen'])
def test_recursos_principales_bloqueados(config, cambio):
    c = copy.deepcopy(config)
    if cambio == 'proyecto': c['name'] = 'novamercado'
    elif cambio == 'volumen': c['volumes']['db']['name'] = 'novamercado_product-db'
    elif cambio == 'externo': c['volumes']['db']['external'] = True
    elif cambio == 'red': c['networks']['default']['name'] = 'novamercado_default'
    elif cambio == 'contenedor': c['services']['api']['container_name'] = 'principal'
    elif cambio == 'bind': c['services']['api']['volumes'][0]['read_only'] = False
    elif cambio == 'tracking': c['services']['api']['environment'] = {'MLFLOW_TRACKING_URI': 'http://host.docker.internal:5001'}
    elif cambio == 'host': c['services']['api']['network_mode'] = 'host'
    elif cambio == 'imagen': c['services']['api'].update(build={'context': '.'}, image='novamercado-api:1.0.0')
    elif cambio == 'puerto': c['services']['api']['ports'][0]['published'] = '8000'
    with pytest.raises(ValueError): validar_config(c, config['name'])


def test_escenario_no_incluye_cambio_de_demanda_en_historico(tmp_path):
    import csv
    from scripts.escenario_resiliencia import generar_escenario, DIAS_HISTORICOS, ventas
    from ml.datos import cargar_datos
    datos = generar_escenario(tmp_path/'datos')
    historial, _ = cargar_datos(datos)
    assert len(historial) == DIAS_HISTORICOS
    assert max(v.ventas for v in historial) < ventas(DIAS_HISTORICOS)
    with (datos/'historico_ventas.csv').open() as f:
        assert all(int(v['ventas']) < 300 for v in csv.DictReader(f))


def test_simulacion_diaria_respeta_orden_y_no_publica_ventas_futuras():
    from datetime import date, timedelta
    from scripts.escenario_resiliencia import simular_dias, DIAS_NUEVOS
    llamadas = []
    class Http:
        def post(self, ruta, json, timeout):
            llamadas.append((ruta, json))
            return type('Respuesta', (), {'status_code':200, 'text':'ok',
                'json':lambda self:{'registros_guardados':1}})()
    siguiente, observacion = simular_dias('http://aislado.test',Http())
    assert len(llamadas) == 2*DIAS_NUEVOS
    for pronostico, observado in zip(llamadas[::2],llamadas[1::2]):
        assert pronostico[0].endswith('/v1/prediccion')
        assert observado[0].endswith('/v1/observaciones')
        assert pronostico[1]['fecha'] == observado[1]['fecha']
        assert 'ventas' not in pronostico[1]
    assert date.fromisoformat(siguiente['fecha']) == date.fromisoformat(observacion['fecha'])+timedelta(days=1)


def test_simulacion_rechaza_respuesta_erronea():
    from scripts.escenario_resiliencia import simular_dias
    class Http:
        def post(self,*args,**kwargs):
            return type('Respuesta',(),{'status_code':422,'text':'Rechazado'})()
    with pytest.raises(AssertionError,match='Rechazado'):
        simular_dias('http://aislado.test',Http())


def test_simulacion_extendida_inyecta_errores_y_reentrena_periodicamente():
    from scripts.escenario_resiliencia import simular_dias, DIAS_NUEVOS
    class Http:
        def __init__(self): self.rechazos = 0
        def post(self, ruta, json, timeout):
            if ('familia_nueva_xyz' in str(json) or
                any(type(v.get('ventas')) is float for v in json.get('ventas', [])) or
                len(json.get('ventas', [])) > 1):
                self.rechazos += 1
                return type('Respuesta', (), {'status_code':422, 'text':'Entrada rechazada',
                    'json':lambda self:{'detail':'error inédito'}})()
            return type('Respuesta', (), {'status_code':200, 'text':'ok',
                'json':lambda self:{'registros_guardados':1}})()
    llamadas = []
    eventos = {}
    http = Http()
    def reentrenar(dias):
        llamadas.append(dias)
        return {'dia_simulado': dias, 'resultado': 'exitoso'}
    simular_dias('http://aislado.test', http, al_periodo=reentrenar,
        inyectar_errores=True, cada_reentrenamiento=35, eventos=eventos)
    assert llamadas == [35, 70, 105]
    assert len(eventos['errores_422']) == 12
    assert {x['caso'] for x in eventos['errores_422']} == {
        'familia_no_catalogada', 'decimal_fraccionario', 'duplicado_contradictorio'}
    assert all(x['status'] == 422 for x in eventos['errores_422'])
    assert http.rechazos == 12
    assert eventos['observaciones_aceptadas'] == DIAS_NUEVOS
