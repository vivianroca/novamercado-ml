"""Artefacto MLflow ejecutable: HGB más calibración de inventario congelada."""

import joblib
import mlflow.pyfunc
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits


class InventarioHGB(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        self.bundle = joblib.load(context.artifacts["bundle"])

    def predict(self, context, model_input, params=None):
        b = self.bundle
        x = model_input[b["features"]].to_numpy(dtype=float)
        familias = x[:, b["features"].index("familia")]
        if any(not np.isfinite(f) or f != int(f) or int(f) not in b["ajustes_codificados"] for f in familias):
            raise ValueError("Código de familia desconocido")
        with threadpool_limits(limits=2):
            esperada = np.maximum(0, b["estimador"].predict(x))
        ajustes = np.array([b["ajustes_codificados"][int(f)] for f in familias])
        sugeridos = np.maximum(0, np.floor(esperada + ajustes + 0.5)).astype(np.int64)
        return pd.DataFrame({"venta_esperada": esperada, "cantidad_sugerida": sugeridos})
