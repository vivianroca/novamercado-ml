"""Adaptador REST v2 Airflow 3.3.2; no entrena ni opera el Registry."""

from urllib.parse import quote
from uuid import uuid4

import httpx

from app.schemas.administracion import EstadoReentrenamiento, InicioReentrenamiento
from app.servicios.interfaces import ServicioNoDisponible


class EjecucionDesconocida(LookupError):
    pass


class ClienteReentrenamientos:
    def __init__(self, base_url, usuario, clave, dag_id="novamercado_reentrenamiento", transporte=None):
        self.base_url = base_url
        self.usuario = usuario
        self.clave = clave
        self.dag_id = dag_id
        self.transporte = transporte

    def _cliente(self):
        if not self.base_url or not self.base_url.startswith(("http://", "https://")) or not self.usuario or not self.clave:
            raise ServicioNoDisponible("Conexión administrativa de Airflow no configurada")
        return httpx.Client(base_url=self.base_url.rstrip("/") + "/", timeout=5,
                            transport=self.transporte, follow_redirects=False)

    def _autenticar(self, cliente):
        respuesta = cliente.post("auth/token", json={"username": self.usuario, "password": self.clave})
        respuesta.raise_for_status()
        token = self._objeto(respuesta)["access_token"]
        if not isinstance(token, str) or not token:
            raise ValueError("Token inválido")
        cliente.headers["Authorization"] = "Bearer " + token

    @staticmethod
    def _objeto(respuesta):
        valor = respuesta.json()
        if not isinstance(valor, dict):
            raise ValueError("Respuesta Airflow mal formada")
        return valor

    @property
    def ruta_dag(self):
        return "api/v2/dags/" + quote(self.dag_id, safe="")

    def iniciar(self):
        identificador = "novamercado_api__" + uuid4().hex
        try:
            with self._cliente() as cliente:
                self._autenticar(cliente)
                dag = cliente.get(self.ruta_dag)
                dag.raise_for_status()
                info = self._objeto(dag)
                if info.get("has_import_errors") is not False or type(info.get("is_paused")) is not bool:
                    raise ValueError("DAG inválido o con errores de importación")
                if info["is_paused"]:
                    activar = cliente.patch(self.ruta_dag, json={"is_paused": False})
                    activar.raise_for_status()
                # Solo un POST: no reintentar triggers para evitar ejecuciones duplicadas.
                ruta = self.ruta_dag + "/dagRuns"
                try:
                    respuesta = cliente.post(ruta, json={"dag_run_id": identificador, "logical_date": None, "conf": {}})
                except httpx.TimeoutException:
                    # Puede haberse creado aunque se haya perdido la respuesta.
                    respuesta = cliente.get(ruta + "/" + quote(identificador, safe=""))
                respuesta.raise_for_status()
                if self._objeto(respuesta).get("dag_run_id") != identificador:
                    raise ValueError("Airflow no confirmó el ID solicitado")
                return InicioReentrenamiento(id=identificador)
        except (httpx.HTTPError, httpx.InvalidURL, ValueError, KeyError, TypeError) as error:
            raise ServicioNoDisponible("No se pudo iniciar el reentrenamiento en Airflow") from error

    def consultar(self, identificador):
        try:
            with self._cliente() as cliente:
                self._autenticar(cliente)
                ruta = self.ruta_dag + "/dagRuns/" + quote(identificador, safe="")
                respuesta = cliente.get(ruta)
                if respuesta.status_code == 404:
                    raise EjecucionDesconocida("Ejecución de reentrenamiento desconocida")
                respuesta.raise_for_status()
                run = self._objeto(respuesta)
                if run.get("dag_run_id") != identificador:
                    raise ValueError("Respuesta de otra ejecución")
                estado = run.get("state")
                if estado in ("queued", "running"):
                    return EstadoReentrenamiento(estado="en_curso")
                if estado not in ("success", "failed"):
                    raise ValueError("Estado Airflow desconocido")
                resultado = cliente.get(ruta + "/taskInstances/finalizar_reentrenamiento/xcomEntries/resultado_reentrenamiento",
                    params={"deserialize": "true", "stringify": "false", "map_index": -1})
                resultado.raise_for_status()
                valor = self._objeto(resultado)["value"]
                esperado = "exitoso" if estado == "success" else "fallido"
                if not isinstance(valor, dict) or valor.get("estado") != esperado:
                    raise ValueError("Falta resultado terminal consistente")
                return EstadoReentrenamiento(estado=esperado, promovido=valor["promovido"],
                                             version=valor["version"], motivo=valor["motivo"])
        except (httpx.HTTPError, httpx.InvalidURL, ValueError, KeyError, TypeError) as error:
            raise ServicioNoDisponible("No se pudo consultar un resultado verificable de Airflow") from error
