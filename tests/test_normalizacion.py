import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.calidad.normalizacion import (
    Catalogos, SolicitudInvalida, normalizar_observaciones, normalizar_prediccion,
)
from app.schemas.solicitudes import SolicitudObservaciones, SolicitudPrediccion


@pytest.fixture
def catalogos():
    return Catalogos(frozenset({5}), frozenset({"abarrotes", "lacteos"}),
                     {"abarrotes": "abarrotes", "lacteos": "lacteos"})


@pytest.fixture
def solicitud():
    return {"tienda_id": 5, "fecha": "2027-01-01", "familias": [
        {"familia_id": "abarrotes", "en_promocion": 0},
        {"familia_id": "lacteos", "en_promocion": 2}]}


def test_valida_sin_mutacion_y_fechas_simuladas(solicitud, catalogos):
    original = copy.deepcopy(solicitud)
    modelo, calidad = normalizar_prediccion(solicitud, catalogos)
    assert solicitud == original
    assert calidad.model_dump() == {"estado": "ok", "observaciones": []}
    assert modelo.model_dump(mode="json") == solicitud


@pytest.mark.parametrize("valor", ["5", "T05", 5.0])
def test_repara_tienda(valor, solicitud, catalogos):
    solicitud["tienda_id"] = valor
    modelo, calidad = normalizar_prediccion(solicitud, catalogos)
    assert modelo.tienda_id == 5
    assert calidad.estado == "corregido"
    assert calidad.observaciones[0].campo == "tienda_id"


@pytest.mark.parametrize("valor", [True, None, -1, 5.1, "T99", {}, []])
def test_rechaza_tienda(valor, solicitud, catalogos):
    solicitud["tienda_id"] = valor
    with pytest.raises(SolicitudInvalida, match="tienda_id") as error:
        normalizar_prediccion(solicitud, catalogos)
    assert error.value.status_code == 422
    assert error.value.detail


@pytest.mark.parametrize("valor", ["01/01/2027", "2027-01-01T00:00:00"])
def test_fecha_reparable(valor, solicitud, catalogos):
    solicitud["fecha"] = valor
    modelo, calidad = normalizar_prediccion(solicitud, catalogos)
    assert modelo.fecha.isoformat() == "2027-01-01"
    assert calidad.estado == "corregido"


@pytest.mark.parametrize("valor", ["2027-02-30", "01/02/27", "2027-01-01T12:00:00", 1700000000])
def test_fecha_invalida(valor, solicitud, catalogos):
    solicitud["fecha"] = valor
    with pytest.raises(SolicitudInvalida, match="fecha"):
        normalizar_prediccion(solicitud, catalogos)


def test_reparaciones_y_advertencia_tienen_trazabilidad(solicitud, catalogos):
    solicitud["familias"] = [{"familia_id": "LÁCTEOS ", "en_promocion": "2"}]
    modelo, calidad = normalizar_prediccion(solicitud, catalogos)
    assert len(modelo.familias) == 1
    assert calidad.estado == "advertencia"
    assert [a.accion for a in calidad.observaciones] == ["reparar", "reparar", "advertir"]
    assert calidad.observaciones[0].campo == "familias[0].familia_id"


@pytest.mark.parametrize("valor", [True, -2, 1.5, "1,292", "1,000", "NaN", float("nan"), float("inf"), None])
def test_no_inventa_cantidades(valor, solicitud, catalogos):
    solicitud["familias"][0]["en_promocion"] = valor
    with pytest.raises(SolicitudInvalida, match="en_promocion"):
        normalizar_prediccion(solicitud, catalogos)


def test_duplicados_canonicos(solicitud, catalogos):
    solicitud["familias"].append({"familia_id": "LÁCTEOS", "en_promocion": 2})
    modelo, calidad = normalizar_prediccion(solicitud, catalogos)
    assert len(modelo.familias) == 2
    assert calidad.estado == "corregido"
    solicitud["familias"][-1]["en_promocion"] = 3
    with pytest.raises(SolicitudInvalida, match="contradictorios"):
        normalizar_prediccion(solicitud, catalogos)


@pytest.mark.parametrize("alteracion", ["extra", "falta", "lista_vacia", "familia_desconocida", "item_extra", "alias_conflictivo"])
def test_estructura_invalida(alteracion, solicitud, catalogos):
    if alteracion == "extra": solicitud["inventado"] = 1
    if alteracion == "falta": del solicitud["fecha"]
    if alteracion == "lista_vacia": solicitud["familias"] = []
    if alteracion == "familia_desconocida": solicitud["familias"][0]["familia_id"] = "otra"
    if alteracion == "item_extra": solicitud["familias"][0]["ventas"] = 3
    if alteracion == "alias_conflictivo": solicitud["tienda"] = 5
    with pytest.raises(SolicitudInvalida):
        normalizar_prediccion(solicitud, catalogos)


def test_observaciones_parciales_y_reenvio(catalogos):
    entrada = {"tienda_id": 5, "fecha": "2025-11-17", "ventas": [{"familia_id": "abarrotes", "ventas": "50,0"}]}
    a = normalizar_observaciones(entrada, catalogos)
    assert a == normalizar_observaciones(entrada, catalogos)
    assert a[0].ventas[0].ventas == 50
    assert a[1].estado == "corregido"
    entrada["ventas"][0]["ventas"] = -4
    with pytest.raises(SolicitudInvalida, match="negativos"):
        normalizar_observaciones(entrada, catalogos)


@pytest.mark.parametrize("clase,campo", [(SolicitudPrediccion, "familias"), (SolicitudObservaciones, "ventas")])
def test_esquemas_rechazan_coercion_implicita(clase, campo):
    medida = "en_promocion" if campo == "familias" else "ventas"
    with pytest.raises(ValidationError):
        clase.model_validate({"tienda_id": "5", "fecha": "2025-11-17", campo: [{"familia_id": "abarrotes", medida: True}]})


EJEMPLOS = Path(__file__).resolve().parents[1] / "data"


@pytest.mark.parametrize("nombre,estado", [
    ("E01_tienda_texto", "corregido"), ("E02_familia_otra_forma", "corregido"),
    ("E03_promocion_texto", "corregido"), ("E04_fecha_formato", "corregido"),
    ("E05_faltan_familias", "advertencia"), ("E06_familia_repetida", "rechazar"),
    ("E07_campo_renombrado", "corregido"), ("E08_ventas_negativas", "rechazar"),
    ("E09_envio_repetido", "ok"), ("E10_numero_formato", "rechazar"),
])
def test_ejemplos_docentes(nombre, estado):
    if not (EJEMPLOS / "tiendas.csv").exists():
        pytest.skip("Insumos GES locales no disponibles; tests sintéticos siguen activos")
    catalogos = Catalogos.desde_directorio(EJEMPLOS)
    entrada = json.loads((EJEMPLOS / "ejemplos" / "errores" / f"{nombre}.json").read_text())
    normalizar = normalizar_observaciones if "ventas" in entrada else normalizar_prediccion
    if estado == "rechazar":
        with pytest.raises(SolicitudInvalida): normalizar(entrada, catalogos)
    else:
        assert normalizar(entrada, catalogos)[1].estado == estado


@pytest.mark.parametrize("nombre,normalizar", [("prediccion_valida", normalizar_prediccion), ("observacion_valida", normalizar_observaciones)])
def test_ejemplos_validos(nombre, normalizar):
    if not (EJEMPLOS / "tiendas.csv").exists():
        pytest.skip("Insumos GES locales no disponibles")
    entrada = json.loads((EJEMPLOS / "ejemplos" / f"{nombre}.json").read_text())
    assert normalizar(entrada, Catalogos.desde_directorio(EJEMPLOS))[1].estado == "ok"
