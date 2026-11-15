"""Datos sintéticos deterministas para aceptación; no cambia modelos ni políticas."""
import csv
from datetime import date, timedelta

INICIO = date(2024, 1, 1)
DIAS_HISTORICOS = 420
DIAS_NUEVOS = 140


def promocion(indice):
    return indice % 3


def ventas(indice):
    dia = INICIO + timedelta(days=indice)
    # Salto de nivel después del histórico: el modelo antiguo queda desactualizado.
    nivel = 120 if indice < DIAS_HISTORICOS else 320
    return nivel + dia.weekday()*8 + promocion(indice)*35


def generar_escenario(destino):
    destino.mkdir(parents=True, exist_ok=True)
    (destino/'tiendas.csv').write_text('tienda_id,nombre,ciudad,departamento,tipo,fecha_apertura\n1,Sintética,Guatemala,Guatemala,express,2023-01-01\n')
    (destino/'familias.csv').write_text('familia_id,nombre\npan,Pan\n')
    (destino/'costos.csv').write_text('familia_id,costo_faltante,costo_sobrante\npan,3,1\n')
    (destino/'feriados.csv').write_text('fecha,nombre,tipo,ambito\n2024-01-01,Año nuevo,feriado,nacional\n')
    with (destino/'historico_ventas.csv').open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['fecha','tienda_id','familia_id','ventas','en_promocion'])
        for i in range(DIAS_HISTORICOS):
            w.writerow([INICIO+timedelta(days=i),1,'pan',ventas(i),promocion(i)])
    return destino


def probar_errores_ineditos(base, http, fecha):
    """Envía entradas fuera de los ejemplos habituales y devuelve sus respuestas 422."""
    casos = [
        ('familia_no_catalogada', '/v1/prediccion', {
            'tienda_id': 1, 'fecha': str(fecha),
            'familias': [{'familia_id': 'familia_nueva_xyz', 'en_promocion': 0}]}),
        ('decimal_fraccionario', '/v1/observaciones', {
            'tienda_id': 1, 'fecha': str(fecha),
            'ventas': [{'familia_id': 'pan', 'ventas': 12.5}]}),
        ('duplicado_contradictorio', '/v1/observaciones', {
            'tienda_id': 1, 'fecha': str(fecha),
            'ventas': [{'familia_id': 'pan', 'ventas': 12},
                       {'familia_id': 'pan', 'ventas': 13}]})
    ]
    respuestas = []
    for nombre, ruta, solicitud in casos:
        respuesta = http.post(base + ruta, json=solicitud, timeout=30)
        assert respuesta.status_code == 422, f'{nombre}: {respuesta.status_code} {respuesta.text}'
        respuestas.append({'caso': nombre, 'ruta': ruta, 'fecha': str(fecha),
                           'status': respuesta.status_code, 'request': solicitud,
                           'response': respuesta.json()})
    return respuestas


def simular_dias(base, http, *, al_periodo=None, inyectar_errores=False,
                 cada_reentrenamiento=35, eventos=None):
    # Pronosticar D, luego recibir observación D antes de pronosticar D+1.
    eventos = eventos if eventos is not None else {}
    observaciones_aceptadas = 0
    for i in range(DIAS_HISTORICOS, DIAS_HISTORICOS+DIAS_NUEVOS):
        offset = i - DIAS_HISTORICOS + 1
        dia = INICIO+timedelta(days=i)
        if inyectar_errores and offset in (14, 49, 84, 119):
            eventos.setdefault('errores_422', []).extend(probar_errores_ineditos(base, http, dia))
        solicitud = {'tienda_id':1,'fecha':str(dia),
            'familias':[{'familia_id':'pan','en_promocion':promocion(i)}]}
        r = http.post(base+'/v1/prediccion',json=solicitud,timeout=30)
        assert r.status_code == 200, r.text
        observacion = {'tienda_id':1,'fecha':str(dia),
            'ventas':[{'familia_id':'pan','ventas':ventas(i)}]}
        r = http.post(base+'/v1/observaciones',json=observacion,timeout=30)
        assert r.status_code == 200 and r.json()['registros_guardados']==1,r.text
        observaciones_aceptadas += r.json()['registros_guardados']
        if al_periodo and offset % cada_reentrenamiento == 0 and offset < DIAS_NUEVOS:
            resultado = al_periodo(offset)
            eventos.setdefault('reentrenamientos_periodicos', []).append(resultado)
    siguiente = {'tienda_id':1,'fecha':str(INICIO+timedelta(days=DIAS_HISTORICOS+DIAS_NUEVOS)),
        'familias':[{'familia_id':'pan','en_promocion':promocion(DIAS_HISTORICOS+DIAS_NUEVOS)}]}
    eventos['dias_simulados'] = DIAS_NUEVOS
    eventos['observaciones_aceptadas'] = observaciones_aceptadas
    return siguiente, observacion
