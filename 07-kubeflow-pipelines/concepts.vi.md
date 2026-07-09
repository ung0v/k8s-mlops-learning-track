> Bản dịch tiếng Việt của `concepts.md` — nếu có chỗ khó hiểu, tham khảo bản tiếng Anh.

# 07 — Khái niệm: Kubeflow Pipelines (KFP v2)

> Đọc phần này trước. Sau đó chạy lab trong `README.md`.
> Đã kiểm chứng với kubeflow.org/docs/components/pipelines — phiên bản KFP mới nhất là `2.16.1`.
> Đây là stage của **pipeline orchestrator chính** (lĩnh vực trọng tâm của bạn).

---

## 1. Pipeline là gì, và tại sao cần một orchestrator?

Trong các stage 04 và 05, chúng ta đã chạy một script huấn luyện duy nhất dưới dạng Job và serve model. Các ML workflow thực tế phức tạp hơn:

```
   download data → preprocess → train → evaluate → validate → register → deploy
```

Mỗi bước là một container. Các bước phụ thuộc lẫn nhau (train cần data đã preprocess).
Một số có thể chạy song song (hyperparameter sweep), một số phải chạy tuần tự. Bạn cần:

- **Một DAG** (directed acyclic graph — đồ thị có hướng không chu trình) của các bước kèm dependencies.
- **Artifact passing** — output của bước A (một file, một metric) trở thành input của bước B.
- **Caching** — nếu bước A không thay đổi, đừng chạy lại.
- **Retry** — nếu một bước thất bại, retry mà không cần chạy lại toàn bộ pipeline.
- **Visualization** — một UI hiển thị DAG, trạng thái từng bước, logs và artifacts.
- **Versioning** — mỗi run được version hóa, để bạn có thể so sánh các run và reproduce.

Một **pipeline orchestrator** cung cấp tất cả những điều trên. **Kubeflow Pipelines (KFP)** là
orchestrator tập trung vào ML phổ biến nhất trên k8s. **Argo Workflows** (stage 08) là orchestrator
tổng quát mà KFP được xây dựng dựa trên đó.

---

## 2. Kiến trúc KFP v2 (standalone trên kind)

KFP standalone chạy các component sau trong namespace `kubeflow`:

```
   ┌──────────────────────────────────────────────────────┐
   │ kubeflow namespace                                   │
   │                                                      │
   │  ml-pipeline (API server)  ←── UI nói chuyện với cái này │
   │  ml-pipeline-ui             ←── web dashboard        │
   │  ml-pipeline-persistence    ←── ghi run metadata    │
   │  minio                      ←── object store tương thích S3 │
   │  mysql                      ←── metadata database    │
   │  workflow-controller        ←── Argo Workflows (chạy các pod thực tế) │
   │  argo-server                ←── Argo Workflows UI/API              │
   └──────────────────────────────────────────────────────┘
```

- **ml-pipeline** — KFP API server. Bạn submit pipeline lên nó qua SDK hoặc UI.
- **ml-pipeline-ui** — dashboard của KFP. Hiển thị pipelines, runs, experiments, artifacts.
- **minio** — object store tương thích S3. Chứa pipeline artifacts (model files, metrics, data).
- **mysql** — lưu run metadata (tên experiment, trạng thái run, parameters).
- **workflow-controller** — Argo Workflows bên dưới. KFP compile pipeline của bạn thành
  Argo Workflow, và workflow controller chạy các Pod thực tế.
- **argo-server** — Argo Workflows API/UI. KFP dùng nó nội bộ.

> **Insight then chốt:** KFP v2 là một **lớp trừu tượng trên Argo Workflows**. Bạn viết pipeline
> bằng Python với KFP SDK; KFP compile chúng thành Argo Workflow YAML; Argo chạy chúng trên k8s.
> Đây là lý do stage 08 (Argo Workflows) là phần tiếp nối — cùng một engine, nhưng tiếp cận trực tiếp.

---

## 3. KFP SDK v2 — viết một pipeline

KFP SDK (Python package `kfp`, v2) cho phép bạn định nghĩa pipeline dưới dạng Python function
được decorate với `@dsl.pipeline`. Mỗi bước là một **component** — một function được container hóa.

### Một component đơn giản

```python
from kfp import dsl

@dsl.component
def train_model(n_estimators: int) -> str:
    import joblib
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.datasets import load_iris
    from sklearn.model_selection import train_test_split

    X, y = load_iris(return_X_y=True)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
    model = RandomForestClassifier(n_estimators=n_estimators)
    model.fit(X_train, y_train)

    joblib.dump(model, "/tmp/model.joblib")
    return "/tmp/model.joblib"
```

Decorator `@dsl.component` biến function thành một component được container hóa. KFP:
1. Inspect signature của function (parameters + return types).
2. Sinh ra một container image (dùng Python environment hiện tại hoặc một base image được chỉ định).
3. Đóng gói code của function vào container đó.
4. Khi pipeline chạy, KFP tạo một Pod thực thi function đó.

### Ghép các component thành một pipeline

```python
from kfp import dsl

@dsl.pipeline(name="iris-train-pipeline")
def iris_pipeline(n_estimators: int = 20):
    train_task = train_model(n_estimators=n_estimators)
    eval_task = evaluate_model(model_path=train_task.output)
    export_task = export_model(model_path=train_task.output, accuracy=eval_task.output)
```

- `train_task.output` — giá trị trả về của `train_model` (đường dẫn model). KFP truyền nó
  làm input cho `evaluate_model`.
- DAG được suy ra ngầm từ data dependencies: `eval` phụ thuộc `train`, `export` phụ thuộc cả hai.
  KFP tự xác định thứ tự.

### Compile pipeline

```python
from kfp.compiler import Compiler
Compiler().compile(iris_pipeline, "iris_pipeline.yaml")
```

Việc này sinh ra một **IR YAML** (intermediate representation — biểu diễn trung gian) — một file YAML
duy nhất chứa toàn bộ định nghĩa pipeline. Bạn submit file này lên KFP qua SDK hoặc UI.

---

## 4. Các khái niệm pipeline (học thuộc bảng này)

| Khái niệm         | Là gì                                                    |
|-------------------|----------------------------------------------------------|
| **Pipeline**      | Một DAG template tái sử dụng (Python function + IR YAML) |
| **Component**     | Một bước duy nhất trong pipeline (function được container hóa) |
| **Run**           | Một lần thực thi pipeline với các parameter cụ thể       |
| **Experiment**    | Một nhóm các run liên quan (vd. "iris-experiments")       |
| **Recurring Run** | Một lịch trình tạo run theo cron (giống CronJob)         |
| **Artifact**      | Một file được tạo/tiêu thụ bởi một bước (model, data, metrics) |
| **Parameter**     | Một giá trị scalar truyền giữa các bước (int, str, float) |
| **Caching**       | Nếu input của một bước không đổi, tái sử dụng output trước đó |

### Artifact so với parameter
- **Parameter** là các giá trị scalar nhỏ (string, int, float). Truyền qua command-line args hoặc env vars.
- **Artifact** là các file (model.joblib, metrics.json, một plot). Lưu trong MinIO, truyền qua URI.

```
   train step ──tạo ra──> model artifact (URI trong MinIO)
                ──truyền──> URI cho eval step
   eval step   ──đọc──>    model artifact từ MinIO
                ──tạo ra──> metrics artifact
```

---

## 5. Cài đặt KFP standalone trên kind

Từ tài liệu chính thức (đã kiểm chứng tháng 7/2026):

```bash
export PIPELINE_VERSION=2.16.1

kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/cluster-scoped-resources?ref=$PIPELINE_VERSION"
kubectl wait --for condition=established --timeout=60s crd/applications.app.k8s.io
kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/env/dev?ref=$PIPELINE_VERSION"
```

- `cluster-scoped-resources` — CRD và cluster roles (apply trước).
- `env/dev` — phiên bản development (MySQL + MinIO + toàn bộ KFP component). Dùng storage
  mặc định (PV/PVC cho MinIO và MySQL). Không bảo mật cho production nhưng hoàn hảo để học.
- Mất khoảng ~3 phút để toàn bộ Pod chuyển sang Ready.

### Truy cập UI

```bash
kubectl port-forward -n kubeflow svc/ml-pipeline-ui 8080:80
```

Mở http://localhost:8080 — dashboard của KFP.

### Yêu cầu tài nguyên
Phiên bản `env/dev` cần:
- ~4 GiB RAM cho toàn bộ KFP pod.
- ~2 CPU core.
- ~10 GiB ổ đĩa (cho MinIO + MySQL + container image).

Kind cluster của bạn với 8 GiB cấp phát cho Docker sẽ xử lý được. Nếu pod bị OOM-killed,
tăng cấp phát bộ nhớ trong Docker Desktop.

---

## 6. Chạy một pipeline

### Qua SDK

```python
from kfp.client import Client

client = Client(host="http://localhost:8080")
run = client.create_run_from_pipeline_package(
    pipeline_file="iris_pipeline.yaml",
    arguments={"n_estimators": 20},
)
```

### Qua UI

1. Mở KFP UI.
2. Bấm "Upload pipeline" → upload `iris_pipeline.yaml`.
3. Bấm "Create run" → đặt parameter → "Start".

### Điều gì xảy ra khi bạn submit một run

```
   SDK/UI ──submit IR YAML──> ml-pipeline API server
                                    │
                                    │ lưu vào MySQL
                                    │ compile thành Argo Workflow YAML
                                    ▼
                              Argo workflow-controller
                                    │
                                    │ tạo Pod cho từng bước (theo thứ tự, theo DAG)
                                    ▼
                              Pod chạy train → eval → export
                                    │
                                    │ artifact lưu trong MinIO
                                    │ metadata lưu trong MySQL
                                    ▼
                              KFP UI hiển thị DAG, trạng thái, artifacts
```

---

## 7. KFP so với Argo Workflows (xem trước stage 08)

| Tính năng            | KFP v2                          | Argo Workflows               |
|----------------------|---------------------------------|------------------------------|
| Đối tượng sử dụng    | Kỹ sư ML                        | DevOps / data engineer       |
| Tác giả pipeline     | Python SDK (`@dsl.pipeline`)    | YAML hoặc Python SDK         |
| Xử lý artifact       | Tích hợp sẵn (MinIO + ML Metadata) | Thủ công (artifact GC, S3) |
| UI                   | Phong phú (DAG, artifact, metric)| Cơ bản (DAG, logs)          |
| Caching              | Tự động (content hash theo bước) | Thủ công (cấu hình)          |
| Engine bên dưới      | Argo Workflows                  | Argo Workflows               |
| Phù hợp nhất cho     | Thí nghiệm ML, huấn luyện model | Data pipeline tổng quát, CI  |

KFP là trừu tượng bậc cao hơn, tập trung vào ML. Argo là engine bậc thấp hơn, mục đích chung.
Trong stage 08 chúng ta sẽ dùng Argo trực tiếp để so sánh.

---

## 8. Những gì bạn có thể giải thích được sau stage 07

- Pipeline orchestrator làm được điều gì mà một k8s Job không làm được.
- Kiến trúc KFP (API server, UI, MinIO, MySQL, Argo controller).
- `@dsl.component` và `@dsl.pipeline` làm gì.
- Khác biệt giữa artifact (file) và parameter (scalar).
- Caching hoạt động thế nào (content hash của input → bỏ qua nếu không đổi).
- Tại sao KFP compile thành Argo Workflow YAML (KFP là trừu tượng trên Argo).
- Cách submit pipeline qua SDK và qua UI.

---

## 9. Đọc thêm

- Cài đặt KFP v2: https://www.kubeflow.org/docs/components/pipelines/v2/installation/
- Khái niệm KFP v2: https://www.kubeflow.org/docs/components/pipelines/v2/concepts/pipeline/
- KFP v2 SDK: https://kubeflow-pipelines.readthedocs.io/en/stable/
- KFP v2 component: https://www.kubeflow.org/docs/components/pipelines/v2/user-guides/components/
- KFP v2 artifact: https://www.kubeflow.org/docs/components/pipelines/v2/user-guides/data-handling/artifacts/
- Triển khai KFP standalone: https://www.kubeflow.org/docs/components/pipelines/v1/installation/standalone-deployment/
- KFP GitHub: https://github.com/kubeflow/pipelines