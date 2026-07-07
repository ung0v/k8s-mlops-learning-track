import joblib
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel
import os

MODEL_PATH = os.environ.get("MODEL_PATH", "/data/model.joblib")

app = FastAPI(title="Iris Classifier")
_model = None

def load_model():
    global _model
    if _model is None:
        if not os.path.exists(MODEL_PATH):
            raise RuntimeError(f"Model not found at {MODEL_PATH}. Run the training Job first (stage 04).")
        _model = joblib.load(MODEL_PATH)
        print(f"Model loaded from {MODEL_PATH}")
    return _model

class IrisFeatures(BaseModel):
    sepal_length: float
    sepal_width: float
    petal_length: float
    petal_width: float

class Prediction(BaseModel):
    class_label: int
    class_name: str

CLASS_NAMES = ["setosa", "versicolor", "virginica"]

@app.get("/health")
def health():
    try:
        load_model()
        return {"status": "ok", "model_loaded": True}
    except Exception as e:
        return {"status": "error", "model_loaded": False, "detail": str(e)}

@app.get("/ready")
def ready():
    load_model()
    return {"ready": True}

@app.post("/predict", response_model=Prediction)
def predict(features: IrisFeatures):
    model = load_model()
    X = np.array([[features.sepal_length, features.sepal_width,
                   features.petal_length, features.petal_width]])
    pred = int(model.predict(X)[0])
    return Prediction(class_label=pred, class_name=CLASS_NAMES[pred])

@app.get("/")
def root():
    return {"app": "iris-classifier", "endpoints": ["/health", "/ready", "/predict"]}