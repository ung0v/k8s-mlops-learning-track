> Bản dịch tiếng Việt của `concepts.md` — nếu có chỗ khó hiểu, tham khảo bản tiếng Anh.

# 04 — Khái niệm: Batch ML jobs (Job, CronJob)

> Đọc phần này trước. Sau đó chạy lab trong `README.md`.
> Đã kiểm chứng với docs k8s v1.36 — `batch/v1` cho cả Job và CronJob.

---

## 1. Tại sao Job tồn tại (và khi nào dùng thay cho Deployment)

Một **Deployment** chạy các Pod mà **không bao giờ dừng** — web server, API, worker
poll queue. Nếu Pod crash, ReplicaSet sẽ restart nó. Nếu Pod hoàn thành công việc và
exit 0, ReplicaSet **vẫn restart nó** (vì `restartPolicy: Always` là mặc định
cho Deployment). Điều đó sai với batch work.

Một **Job** chạy các Pod mà **nên dừng khi công việc xong**. Khi Pod exit 0,
Job coi nó thành công và **không** restart. Khi Pod exit non-zero, Job
retry (tới `backoffLimit`). Khi tất cả completion được yêu cầu hoàn tất, Job ở trạng thái `Complete`.

| Workload     | Pod exit 0           | Pod exit non-0          | Use case              |
|--------------|----------------------|-------------------------|-----------------------|
| Deployment   | Restart Pod          | Restart Pod             | Web server, API      |
| Job          | Đánh dấu thành công  | Retry tới backoffLimit  | Training, batch, ETL  |
| CronJob      | (tạo Job theo lịch)  | (Job retry)             | Nightly retrain       |

Với MLOps, Job là lựa chọn tự nhiên cho:
- Train một model (chạy một lần, tạo artifact, exit).
- Batch inference (xử lý một file, ghi prediction, exit).
- Data preprocessing (ETL trước khi train).
- Hyperparameter sweep (Job song song với param khác nhau).

---

## 2. Tài nguyên Job

### Manifest, từng field

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: iris-train
spec:
  backoffLimit: 4
  activeDeadlineSeconds: 300
  completions: 1
  parallelism: 1
  template:
    metadata:
      labels:
        app: iris-train
    spec:
      restartPolicy: OnFailure
      containers:
      - name: train
        image: iris-train:0.1
        imagePullPolicy: IfNotPresent
        env:
        - name: N_ESTIMATORS
          value: "20"
        - name: MODEL_PATH
          value: /data/model.joblib
        volumeMounts:
        - name: data
          mountPath: /data
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: model-pvc
```

Các field chính:
- `apiVersion: batch/v1` — batch API (không phải `apps/v1` như Deployment).
- `spec.backoffLimit: 4` — retry tối đa 4 lần khi thất bại (mặc định 6). Sau đó, Job được đánh dấu `Failed`.
- `spec.activeDeadlineSeconds: 300` — kill Job nếu chạy lâu hơn 5 phút. Ngăn training chạy lan tràn.
- `spec.completions: 1` — số Pod completion thành công mà Job cần. Mặc định 1.
- `spec.parallelism: 1` — số Pod chạy song song. Mặc định 1. Đặt >1 cho parallel job.
- `spec.template` — Pod template. Cấu trúc giống template của Deployment.
- `spec.template.spec.restartPolicy: OnFailure` — restart Pod **in-place** khi thất bại (cùng đối tượng Pod, containerd restart container). Lựa chọn thay thế `Never` nghĩa là Job tạo Pod **mới** khi thất bại (hữu ích khi muốn môi trường sạch cho mỗi retry).

> **Quan trọng:** `restartPolicy` cho Job phải là `OnFailure` hoặc `Never`. Không thể là `Always` (dành cho Deployment). Nếu đặt `Always`, API server sẽ từ chối Job.

### Trạng thái Pod với Job
- `STATUS: Completed` — Pod exit 0. Job xong.
- `STATUS: Error` — Pod exit non-0 và `restartPolicy: Never` (Pod mới sẽ được tạo tới `backoffLimit`).
- `STATUS: CrashLoopBackOff` — Pod liên tục crash và `restartPolicy: OnFailure` đang restart in-place. Cuối cùng Job bỏ cuộc sau `backoffLimit`.

### `kubectl get job`
```
NAME         COMPLETIONS   DURATION   AGE
iris-train   1/1           12s        30s
```
`COMPLETIONS: 1/1` nghĩa là 1 trong 1 completion được yêu cầu đã thành công. `DURATION` là thời gian Job chạy.

---

## 3. Parallel Job (hyperparameter sweep)

Cho một sweep, bạn muốn N Pod chạy song song, mỗi Pod với param khác. Hai pattern:

### Pattern A: Nhiều Job (mỗi bộ param một Job)
Tạo N Job manifest (hoặc một Job với `completions: N, parallelism: N` và Pod indexed).
Mỗi Pod dùng env var `JOB_COMPLETION_INDEX` (k8s tự set cho indexed Job) để
chọn param từ một ConfigMap.

### Pattern B: Indexed Job
```yaml
spec:
  completions: 5
  parallelism: 5
  completionMode: Indexed
```
Mỗi Pod nhận `JOB_COMPLETION_INDEX` (0-4). Pod đọc param từ ConfigMap được key
theo index. Đây là pattern sạch nhất cho hyperparameter sweep.

Chúng ta sẽ không build một sweep đầy đủ trong lab này (chỉ trình bày về mặt khái niệm); lab chạy một
training Job đơn lẻ, rồi CronJob retrain hằng đêm.

---

## 4. CronJob — Job theo lịch

Một **CronJob** tạo Job theo lịch (cron format). Use case:
- Nightly model retrain.
- Hourly data refresh.
- Daily batch inference.

### Manifest

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: iris-retrain
spec:
  schedule: "*/2 * * * *"
  jobTemplate:
    spec:
      backoffLimit: 2
      template:
        spec:
          restartPolicy: OnFailure
          containers:
          - name: train
            image: iris-train:0.1
            imagePullPolicy: IfNotPresent
            env:
            - name: N_ESTIMATORS
              value: "30"
            volumeMounts:
            - name: data
              mountPath: /data
          volumes:
          - name: data
            persistentVolumeClaim:
              claimName: model-pvc
```

Các field chính:
- `spec.schedule: "*/2 * * * *"` — cron format: phút giờ ngày-of-tháng tháng ngày-of-tuần. Chạy mỗi 2 phút (cho lab; production sẽ là `0 2 * * *` cho 2 AM hằng ngày).
- `spec.jobTemplate` — một Job spec lồng trong CronJob. Mỗi lần chạy theo lịch tạo một Job mới từ template này.
- `spec.concurrencyPolicy` — `Allow` (mặc định), `Forbid` (không start Job mới nếu Job trước vẫn đang chạy), hoặc `Replace` (cancel Job đang chạy và start Job mới). Cho training, dùng `Forbid` để tránh ghi đè lên model.
- `spec.successfulJobsHistoryLimit` / `failedJobsHistoryLimit` — giữ lại bao nhiêu Job đã hoàn thành/thất bại để kiểm tra (mặc định 3/1).

### Bảng tham chiếu cron format
```
┌──────── minute (0-59)
│ ┌────── hour (0-23)
│ │ ┌──── day of month (1-31)
│ │ │ ┌── month (1-12)
│ │ │ │ ┌ day of week (0-6, Sun=0)
│ │ │ │ │
* * * * *
```
- `0 2 * * *` — 2 AM hằng ngày
- `*/2 * * * *` — mỗi 2 phút (lab)
- `0 0 1 * *` — nửa đêm ngày đầu mỗi tháng
- `0 */4 * * 1-5` — mỗi 4 giờ trong ngày thường

---

## 5. Chia sẻ model artifact qua PVC

Training Job và serving Deployment (stage 05) cần chia sẻ file model. Hai
lựa chọn:

### (a) PVC (sẽ dùng)
Job ghi `model.joblib` vào PVC. Serving Deployment mount **cùng** PVC (read-only)
và load model lúc startup. Đơn giản, hoạt động trên một node. Lưu ý: nếu Job và
serving Pod ở các node khác nhau, PVC phải là `ReadWriteMany` (NFS) hoặc cần
distributed filesystem. Trên single-node kind, `ReadWriteOnce` là đủ.

### (b) Object storage (pattern production)
Job upload model lên S3/MinIO/artifact registry. Serving Pod download nó lúc
startup (hoặc init container làm việc đó). Đây là cách MLflow + stage 09/10 sẽ làm sau.

Cho stage này, ta dùng PVC — pattern đơn giản nhất minh hoạ ý tưởng. Stage 09
thay PVC bằng artifact store của MLflow.

---

## 6. Mô hình tư duy

```
   kubectl apply -f job.yaml
        │
        ▼
   Job controller (in controller-manager)
        │  creates a Pod from job.spec.template
        ▼
   Pod runs: python train.py
        │  writes /data/model.joblib (PVC)
        │  exits 0
        ▼
   Job controller sees exit 0
        │  marks Job COMPLETIONS 1/1
        │  does NOT restart the Pod (unlike a Deployment)
        ▼
   PVC now has the model
        │
        ▼
   (later, stage 05) Serving Deployment mounts the same PVC
       └─> loads model.joblib at startup
```

Với CronJob, CronJob controller thức dậy theo lịch, tạo một Job mới (tạo
Pod mới), và chu trình lặp lại.

---

## 7. Những gì bạn cần giải thích được sau stage 04

- Tại sao Job (không phải Deployment) là công cụ đúng cho training.
- `backoffLimit`, `completions`, `parallelism` nghĩa là gì.
- Tại sao `restartPolicy: OnFailure` (không phải `Always`) cho Job.
- Cron format và cách lên lịch retrain 2 AM hằng ngày.
- `concurrencyPolicy: Forbid` làm gì và tại sao quan trọng với training.
- Cách Job và serving Pod chia sẻ model qua PVC.
- Toàn bộ chuỗi từ `kubectl apply -f job.yaml` đến "file model trên PVC".

---

## 8. Đọc thêm (docs chính thức)

- Jobs: https://kubernetes.io/docs/concepts/workloads/controllers/job/
- CronJobs: https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/
- Run a Job: https://kubernetes.io/docs/concepts/workloads/controllers/job/#running-an-example-job
- Indexed Job for parallel processing: https://kubernetes.io/docs/tasks/job/indexed-parallel-processing-static/
- Pod restartPolicy: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#restart-policy
- Cron format (Wikipedia): https://en.wikipedia.org/wiki/Cron