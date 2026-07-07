# 03 — Khái niệm: Đóng gói ML apps cho Kubernetes

> Bản dịch tiếng Việt của `concepts.md` — nếu có chỗ khó hiểu, tham khảo bản tiếng Anh.
> Đọc phần này trước. Sau đó chạy lab trong `README.md`.
> Stage này không có manifest riêng — nó dạy pattern build image mà stage 04 và 05 sử dụng.

---

## 1. Tại sao đóng gói quan trọng cho ML trên k8s

Mọi Pod đều chạy một container, và mọi container đều chạy một image. Trên kind bạn không thể `docker pull`
từ registry trong lúc lab (chúng ta không có registry) — bạn build image trên Mac, rồi
`kind load docker-image` để đẩy nó vào containerd của node kind. Điều này có nghĩa là:

1. Image phải tự chứa: code app + dependencies + Python runtime.
2. Image phải đủ nhỏ để load nhanh và không lãng phí disk của node kind.
3. Image phải chạy bằng user non-root (best practice về bảo mật, được yêu cầu bởi nhiều Pod Security Standards).
4. Image phải nhận cấu hình qua env vars (để k8s ConfigMaps/Secrets có thể inject).

Stage này dạy pattern **multi-stage build** — cách tiêu chuẩn để đạt cả bốn mục tiêu trên.

---

## 2. Vấn đề của single-stage

Hãy xem `00-existing-flask-baseline/Dockerfile` hiện có:

```dockerfile
FROM python:3.8.8-slim-buster
WORKDIR /app
COPY . app.py /app/
RUN pip install --no-cache-dir --upgrade pip &&\
    pip install --no-cache-dir -r requirements.txt
EXPOSE 8080
ENTRYPOINT [ "python" ]
CMD [ "app.py" ]
```

Các vấn đề:
- **Base image cũ** (`python:3.8.8-slim-buster` — 3.8 đã EOL, buster là Debian 10, cũng đã EOL).
- **pip cache + build deps** vẫn nằm trong image cuối (làm image phình to).
- **Chạy bằng root** (mặc định cho `python:3.x-slim`) — rủi ro bảo mật.
- **`COPY . app.py /app/`** có lỗi đánh máy (copy cả `.` và `app.py` — `.` thắng, `app.py` bị coi là tên thư mục đích). Đây là bug của repo gốc.
- **Không có resource limits** được nhúng sẵn (k8s sẽ set, nhưng image nên gọn nhẹ).

Một ML image naïve dựa trên `python:3.12` (không phải slim) + `pip install scikit-learn` sẽ có kích thước khoảng 1.5 GB. Chúng ta có thể làm tốt hơn.

---

## 3. Pattern multi-stage build

Một **multi-stage Dockerfile** có nhiều dòng `FROM`. Mỗi `FROM` bắt đầu một build stage mới.
Chỉ **stage cuối** trở thành image; các stage trước bị loại bỏ. Bạn chỉ copy những gì
cần từ các stage trước bằng `COPY --from=<stage>`.

```
   Stage 1 (builder)              Stage 2 (final)
   ┌─────────────────────┐        ┌─────────────────────┐
   │ python:3.12-slim    │        │ python:3.12-slim    │
   │ + pip install ...   │  COPY  │ (no pip, no cache)  │
   │ + build tools       │ ─────> │ + only the installed│
   │ (gcc, wheels, etc.) │        │   packages + app.py │
   │ ~500 MB             │        │ ~150 MB             │
   └─────────────────────┘        └─────────────────────┘
```

### Dockerfile cho training image (stage 04)

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build
COPY src/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY src/train.py .
ENTRYPOINT ["python", "train.py"]
```

Giải thích từng dòng:
- `FROM python:3.12-slim AS builder` — đặt tên cho stage đầu là `builder`. `slim` là Debian bookworm chỉ có Python, không có build tools.
- `WORKDIR /build` — đặt thư mục làm việc bên trong stage.
- `COPY src/requirements.txt .` — copy trước chỉ file requirements. Docker cache layer này; nếu requirements không đổi, layer pip install sẽ được tái sử dụng ở mọi lần build.
- `RUN pip install --no-cache-dir --prefix=/install -r requirements.txt` — cài các package vào `/install` (không phải `/usr/local` mặc định). `--no-cache-dir` ngăn pip ghi wheel cache (sẽ làm layer phình to).
- `FROM python:3.12-slim` — bắt đầu stage cuối. Base mới, sạch sẽ.
- `COPY --from=builder /install /usr/local` — copy các package đã cài từ builder stage vào Python path của image cuối. Không có pip, không có build tools, không có cache — chỉ có các package đã cài.
- `COPY src/train.py .` — copy chỉ code app.
- `ENTRYPOINT ["python", "train.py"]` — câu lệnh. Khi k8s chạy image này, nó chạy `python train.py`.

### Dockerfile cho serving image (stage 05)

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build
COPY src/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY src/app.py .
EXPOSE 8000
USER 1000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

Hai điểm khác biệt so với training image:
- `USER 1000` — chạy bằng UID 1000 (non-root). Pod Security Standards `restricted` của k8s yêu cầu điều này. Nếu container ghi vào một mounted volume, volume đó phải cho phép UID 1000 ghi.
- `CMD ["uvicorn", ...]` thay vì ENTRYPOINT. CMD có thể bị override bởi `command`/`args` của Pod spec trong k8s; ENTRYPOINT khó override hơn. Đối với server, CMD là quy ước.

### Tại sao `--prefix=/install` + `COPY --from=builder`?
Nếu bạn `pip install` vào `/usr/local` mặc định, bản install sẽ kéo thêm chính pip + setuptools + wheel + cache. Copy `/install` (chỉ chứa cây package) vào `/usr/local` của stage cuối cho bạn các package mà không có phần cài đặt phình to. Đây là cách sạch nhất để có một image Python nhỏ.

---

## 4. Kích thước image — tại sao chúng ta quan tâm

| Image | Kích thước | Có gì bên trong |
|-------|-----------|-----------------|
| `python:3.12` | ~1 GB | Debian đầy đủ + Python + build tools |
| `python:3.12-slim` | ~150 MB | Debian slim + Python (không có build tools) |
| `python:3.12-alpine` | ~50 MB | Alpine + Python (musl libc, một số package không hoạt động) |
| Image sklearn multi-stage của chúng ta | ~200 MB | slim + sklearn/joblib/numpy đã cài (không có pip, không có cache) |

Đối với một Mac chạy kind, mỗi MB đều quan trọng: `kind load docker-image` copy image từ Docker vào container của node kind. Một image 1.5 GB mất hơn 30 giây để load; một image 200 MB load trong 5 giây.

### Tại sao không dùng Alpine?
Alpine dùng `musl` libc thay vì `glibc`. Nhiều wheel Python (numpy, scipy, pandas, sklearn) được build dựa trên glibc và sẽ không hoạt động trên Alpine nếu không biên dịch lại từ source — điều này lại đưa build tools trở lại và làm mất lợi thế về kích thước. Với ML, hãy dùng `slim` (dựa trên Debian).

---

## 5. `kind load docker-image` — registry thay thế

Trên một cluster thực bạn sẽ push lên registry (`docker push myregistry.com/myapp:v1`) và Pod spec sẽ tham chiếu image đó. Trên kind không có registry. Thay vào đó:

```bash
docker build -t iris-train:0.1 .
kind load docker-image iris-train:0.1
```

`kind load docker-image` lấy image từ Docker trên Mac, đóng gói nó thành tar, và `docker exec` vào container của node kind để `ctr images import`. Sau đó, containerd của node kind có image và các Pod có thể dùng nó.

Trong manifest Pod/Job/Deployment, set `imagePullPolicy: Never` (hoặc `IfNotPresent`) để kubelet không cố pull từ registry — nó chỉ dùng image local.

```yaml
spec:
  containers:
  - name: train
    image: iris-train:0.1
    imagePullPolicy: IfNotPresent
```

> **Gotcha:** nếu bạn rebuild image với cùng tag (`iris-train:0.1`), bạn phải chạy lại `kind load docker-image` — kind không tự đồng bộ. Nếu tag là `:latest`, set `imagePullPolicy: Never` để ngăn kubelet cố pull (nó luôn pull `:latest` theo mặc định).

---

## 6. Chạy bằng non-root

Các cluster k8s production áp dụng **Pod Security Standards** — mức `restricted` yêu cầu container chạy bằng non-root. Ngay cả trên kind (mặc định là `privileged`), chạy bằng non-root vẫn là thói quen tốt.

Trong Dockerfile:
```dockerfile
USER 1000
```

Điều này khiến mọi process trong container chạy bằng UID 1000. Hệ quả:
- Container không thể ghi vào `/root` hoặc `/var/log`.
- Nếu app ghi vào một PVC đã mount, filesystem của PVC phải cho phép UID 1000 ghi. Trên StorageClass `local-path` của kind, thư mục được tạo với mode 0777, nên điều này hoạt động.

Trong Pod spec (sẽ đề cập ở stage 05), bạn cũng có thể set `securityContext`:
```yaml
spec:
  securityContext:
    runAsUser: 1000
    runAsNonRoot: true
```

---

## 7. Cấu hình qua env vars — pattern 12-factor

Script training đọc cấu hình của nó từ env vars với các default hợp lý:

```python
MODEL_PATH = os.environ.get("MODEL_PATH", "/data/model.joblib")
N_ESTIMATORS = int(os.environ.get("N_ESTIMATORS", "20"))
```

Điều này cho phép bạn override cấu hình trong manifest k8s mà không cần rebuild image:

```yaml
spec:
  containers:
  - name: train
    image: iris-train:0.1
    env:
    - name: N_ESTIMATORS
      value: "50"
    - name: MODEL_PATH
      value: /data/model.joblib
```

Đây là pattern **12-factor app** (cấu hình trong môi trường, không hardcode). Đó là lý do k8s có ConfigMaps và Secrets — chúng inject env vars vào Pod.

---

## 8. Vòng lặp build → load → run

Vòng lặp đầy đủ cho bất kỳ custom image nào trên kind:

```
   edit code ──> docker build -t <name>:<tag> .
              ──> kind load docker-image <name>:<tag>
              ──> kubectl apply -f manifest.yaml   (image: <name>:<tag>, imagePullPolicy: IfNotPresent)
              ──> kubectl get pods  (watch it run)
```

Nếu bạn sửa code, hãy rebuild với một **tag mới** (hoặc cùng tag + re-load). Nếu Pod được quản lý bởi một Deployment, dùng `kubectl rollout restart deployment/<name>` để ép re-pull.

---

## 9. Những gì bạn cần giải thích được sau stage 03

- Tại sao một Python image single-stage bị phình to (pip cache, build tools).
- Cách một multi-stage Dockerfile hoạt động (builder stage + final stage, `COPY --from`).
- Tại sao `python:3.12-slim` là base phù hợp cho ML (không phải alpine, không phải full).
- Cách `kind load docker-image` thay thế registry.
- Tại sao `imagePullPolicy: IfNotPresent` cần thiết cho image local.
- Tại sao `USER 1000` quan trọng đối với Pod Security.
- Pattern config 12-factor (env vars với default).

---

## 10. Đọc thêm

- Docker multi-stage builds: https://docs.docker.com/build/building/multi-stage/
- kind load docker-image: https://kind.sigs.k8s.io/docs/user/quick-start/#loading-an-image-into-the-cluster
- Kubernetes imagePullPolicy: https://kubernetes.io/docs/concepts/containers/images/
- Pod Security Standards: https://kubernetes.io/docs/concepts/security/pod-security-standards/
- 12-factor app (config): https://12factor.net/config
- Slim Python images: https://hub.docker.com/_/python (xem "Image variants" → slim)