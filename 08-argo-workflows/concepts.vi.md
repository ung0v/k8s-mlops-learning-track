> Bản dịch tiếng Việt của `concepts.md` — nếu có chỗ khó hiểu, tham khảo bản tiếng Anh.

# 08 — Khái niệm: Argo Workflows

> Đọc phần này trước. Sau đó chạy lab trong `README.md`.
> Đã kiểm tra với argo-workflows.readthedocs.io — cài đặt qua `quick-start-minimal.yaml`.
> Đây là phần **tiếp nối** của KFP (stage 07) — Argo là engine mà KFP được xây dựng trên.

---

## 1. Argo Workflows là gì?

**Argo Workflows** là một workflow orchestrator mục đích chung cho Kubernetes. Bạn định nghĩa
một **DAG** (hoặc steps) của các container, và Argo chạy chúng dưới dạng Pod, xử lý:
- Phụ thuộc giữa các steps (A trước B).
- Thực thi song song (B và C cùng lúc sau A).
- Truyền artifact (A tạo ra một file, B đọc file đó).
- Thử lại khi thất bại.
- Tạm dừng/tiếp tục.
- Một UI hiển thị DAG và logs.

Đây là **cùng engine mà KFP sử dụng** — khi bạn submit một KFP pipeline, KFP biên dịch nó thành
một Argo Workflow YAML, và Argo workflow controller chạy nó. Stage 08 dùng Argo trực tiếp,
để bạn thấy engine thô mà không qua lớp trừu tượng của KFP.

### Tại sao dùng Argo trực tiếp thay vì KFP?
- **Đơn giản** — một file YAML, không cần Python SDK, không cần bước biên dịch.
- **Mục đích chung** — không dành riêng cho ML. Phù hợp cho data pipeline, CI, batch job.
- **Overhead thấp hơn** — cài đặt Argo khoảng ~3 pod; KFP là ~10+ pod.
- **Kiểm soát trực tiếp** — bạn thấy chính xác Pod nào được tạo, args gì được truyền.

### Tại sao KFP hơn Argo cho ML?
- **Theo dõi artifact** — Tích hợp MinIO + ML Metadata của KFP được xây dựng sẵn. Trong Argo
  bạn phải cấu hình truyền artifact thủ công.
- **Python SDK** — `@dsl.component` của KFP thuận tiện hơn YAML cho pipeline phức tạp.
- **Caching** — KFP tự động cache; trong Argo bạn phải cấu hình.
- **UI chuyên cho ML** — UI của KFP hiển thị artifact, metric, model lineage.

---

## 2. Kiến trúc Argo Workflows

```
   ┌─────────────────────────────────────────────┐
   │ argo namespace                              │
   │                                             │
   │  argo-server        ←── API + UI (port 2746)│
   │  workflow-controller ←── the reconcile loop │
   │  (optional: minio for artifacts)           │
   └─────────────────────────────────────────────┘
```

- **argo-server** — REST API + web UI. Bạn submit workflow thông qua nó. Port 2746 (https).
- **workflow-controller** — theo dõi `Workflow` CRD, tạo Pod cho mỗi step, theo dõi trạng thái.
- Không có MySQL, không có MinIO theo mặc định (cài đặt `quick-start-minimal` thực sự tối giản).

CRD chính là `Workflow` (`argoproj.io/v1alpha1`). Một Workflow nói: "chạy DAG các container này."

---

## 3. Workflow YAML

Có hai cách để định nghĩa một workflow:

### (a) Steps (tham chiếu template tuần tự/song song)
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: iris-steps-
spec:
  entrypoint: main
  templates:
  - name: main
    steps:
    - - name: train
        template: train
    - - name: eval
        template: eval
        arguments:
          artifacts:
          - name: model
            from: "{{steps.train.outputs.artifacts.model}}"
  - name: train
    container:
      image: iris-train:0.1
      ...
  - name: eval
    container:
      image: iris-eval:0.1
      ...
```

`- -` (hai dấu gạch) = steps song song. `-` (một dấu gạch) = tuần tự. Mỗi step tham chiếu
một template (một định nghĩa container).

### (b) DAG (phụ thuộc tường minh)
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: iris-dag-
spec:
  entrypoint: main
  templates:
  - name: main
    dag:
      tasks:
      - name: train
        template: train
      - name: eval
        template: eval
        dependencies: [train]
        arguments:
          artifacts:
          - name: model
            from: "{{tasks.train.outputs.artifacts.model}}"
      - name: export
        template: export
        dependencies: [eval]
```

DAG rõ ràng hơn cho pipeline phức tạp. Lab này sẽ dùng DAG.

### Các trường quan trọng
- `spec.entrypoint` — template nào để bắt đầu.
- `spec.templates[]` — các định nghĩa container có thể tái sử dụng.
- `templates[].dag.tasks[].dependencies` — danh sách task phải hoàn thành trước.
- `templates[].dag.tasks[].template` — template nào để chạy cho task này.
- `templates[].dag.tasks[].arguments.artifacts` — đầu vào cho task (từ output của task khác).

---

## 4. Truyền artifact trong Argo

Argo có **artifact support** tích hợp sẵn. Một template có thể khai báo:
- `outputs.artifacts` — file mà container tạo ra (Argo upload lên artifact store).
- `inputs.artifacts` — file mà container cần (Argo download từ store).

Theo mặc định, cài đặt `quick-start-minimal` dùng **emptyDir** cho artifact (tạm thời,
trên node của Pod). Dùng cho production bạn nên cấu hình S3/MinIO làm artifact store.

```yaml
- name: train
  container:
    image: iris-train:0.1
    outputs:
      artifacts:
      - name: model
        path: /tmp/model.joblib
```

Sau đó trong task eval:
```yaml
- name: eval
  inputs:
    artifacts:
    - name: model
      path: /tmp/model.joblib
  container:
    image: iris-eval:0.1
```

Argo tự động:
1. Sau khi Pod của train hoàn thành, upload `/tmp/model.joblib` lên artifact store.
2. Trước khi Pod của eval khởi chạy, download artifact về `/tmp/model.joblib`.

`from: "{{tasks.train.outputs.artifacts.model}}"` trong arguments của task kết nối chúng.

---

## 5. Cài đặt Argo Workflows trên kind

Từ quick start chính thức:

```bash
kubectl create namespace argo
kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.6.4/quick-start-minimal.yaml
```

> **Lưu ý:** Kiểm tra https://github.com/argoproj/argo-workflows/releases cho phiên bản mới nhất.
> Manifest `quick-start-minimal` bao gồm workflow controller + argo-server + RBAC tối thiểu.

Chờ pod:

```bash
kubectl wait --for=condition=Ready pod -l app=argo-server -n argo --timeout=120s
kubectl wait --for=condition=Ready pod -l app=workflow-controller -n argo --timeout=120s
```

Truy cập UI:

```bash
kubectl -n argo port-forward service/argo-server 2746:2746
```

Mở https://localhost:2746 (chấp nhận self-signed cert).

---

## 6. KFP vs Argo — cùng engine, khác abstraction

Khi bạn chạy KFP pipeline trong stage 07, phía hậu trường:
1. KFP biên dịch `pipeline.py` thành IR YAML → sau đó thành **Argo Workflow** YAML.
2. Argo workflow-controller (do KFP cài đặt) tạo Pod cho mỗi step.
3. Artifact đi đến MinIO (do KFP cấu hình).

Trong stage 08, bạn viết Workflow YAML trực tiếp. Sự khác biệt:

| Cái gì          | KFP (stage 07)             | Argo (stage 08)              |
|-----------------|---------------------------|------------------------------|
| Tác giả         | Python `@dsl.pipeline`    | YAML `Workflow`              |
| Biên dịch       | `kfp compiler` → IR YAML  | không (YAML là source)       |
| Artifact store  | MinIO (tự cấu hình)       | emptyDir hoặc cấu hình S3 thủ công |
| UI              | KFP dashboard             | Argo UI                      |
| Caching         | Tự động                   | Thủ công (cấu hình cache)    |
| Metadata        | ML Metadata (MySQL)       | Không có sẵn                 |
| Controller pod  | KFP's workflow-controller | Cùng workflow-controller      |

workflow-controller thực sự là cùng một binary. KFP chỉ bọc nó với tooling chuyên cho ML
(MinIO, ML Metadata, Python SDK).

---

## 7. Bạn nên giải thích được gì sau stage 08

- Argo Workflows là gì và khác KFP thế nào.
- Hai cách định nghĩa workflow (steps vs DAG).
- Truyền artifact hoạt động thế nào trong Argo (outputs.artifacts → inputs.artifacts).
- Tại sao KFP là "Argo + ML tooling" (cùng controller, thêm abstraction).
- Khi nào dùng Argo trực tiếp vs KFP cho một ML pipeline thực tế.

---

## 8. Đọc thêm

- Argo Workflows quick start: https://argo-workflows.readthedocs.io/en/stable/quick-start/
- Argo Workflows examples: https://github.com/argoproj/argo-workflows/tree/main/examples
- Argo Workflows CLI: https://argo-workflows.readthedocs.io/en/stable/walk-through/argo-cli/
- Argo Workflows DAG: https://argo-workflows.readthedocs.io/en/stable/walk-through/dag/
- Argo Workflows artifacts: https://argo-workflows.readthedocs.io/en/stable/walk-through/artifacts/
- Argo Workflows installation: https://argo-workflows.readthedocs.io/en/stable/installation/