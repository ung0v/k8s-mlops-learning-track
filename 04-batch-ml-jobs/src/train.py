import numpy as np
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import joblib
import os
import json

MODEL_PATH = os.environ.get("MODEL_PATH", "/data/model.joblib")
METRICS_PATH = os.environ.get("METRICS_PATH", "/data/metrics.json")
N_ESTIMATORS = int(os.environ.get("N_ESTIMATORS", "20"))
MAX_DEPTH = int(os.environ.get("MAX_DEPTH", "3"))
RANDOM_STATE = int(os.environ.get("RANDOM_STATE", "42"))

def train():
    print(f"Loading iris dataset (n_estimators={N_ESTIMATORS}, max_depth={MAX_DEPTH})")
    X, y = load_iris(return_X_y=True)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE
    )

    model = RandomForestClassifier(
        n_estimators=N_ESTIMATORS,
        max_depth=MAX_DEPTH,
        random_state=RANDOM_STATE,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"Test accuracy: {acc:.4f}")

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")

    metrics = {
        "accuracy": float(acc),
        "n_estimators": N_ESTIMATORS,
        "max_depth": MAX_DEPTH,
        "n_train": len(X_train),
        "n_test": len(X_test),
    }
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"Metrics saved to {METRICS_PATH}")

    return acc

if __name__ == "__main__":
    train()