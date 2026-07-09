from kfp import dsl
from kfp.dsl import Output, Input, Artifact, Model, Metrics


@dsl.component
def train_model(n_estimators: int, max_depth: int, model: Output[Model]):
    import joblib
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.datasets import load_iris
    from sklearn.model_selection import train_test_split

    X, y = load_iris(return_X_y=True)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    clf = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=42,
    )
    clf.fit(X_train, y_train)

    joblib.dump(clf, model.path)
    model.metadata["framework"] = "sklearn"
    model.metadata["n_estimators"] = n_estimators


@dsl.component
def evaluate_model(model: Input[Model], metrics: Output[Metrics]) -> float:
    import joblib
    from sklearn.metrics import accuracy_score
    from sklearn.datasets import load_iris
    from sklearn.model_selection import train_test_split

    clf = joblib.load(model.path)

    X, y = load_iris(return_X_y=True)
    _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    acc = accuracy_score(y_test, clf.predict(X_test))
    metrics.log_metric("accuracy", float(acc))
    metrics.log_metric("n_features", X_test.shape[1])

    return float(acc)


@dsl.component
def export_model(model: Input[Model], accuracy: float):
    print(f"Exporting model with accuracy: {accuracy:.4f}")
    print(f"Model path: {model.path}")
    print(f"Model metadata: {model.metadata}")
    print("Model ready for serving")


@dsl.pipeline(name="iris-train-pipeline", description="Train, evaluate, and export an iris classifier")
def iris_pipeline(n_estimators: int = 20, max_depth: int = 3):
    train_task = train_model(n_estimators=n_estimators, max_depth=max_depth)
    eval_task = evaluate_model(model=train_task.outputs["model"])
    export_task = export_model(
        model=train_task.outputs["model"],
        accuracy=eval_task.output,
    )


if __name__ == "__main__":
    from kfp.compiler import Compiler
    Compiler().compile(iris_pipeline, "iris_pipeline.yaml")
    print("Pipeline compiled to iris_pipeline.yaml")