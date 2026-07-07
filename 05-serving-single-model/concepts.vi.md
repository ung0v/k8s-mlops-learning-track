> Bản dịch tiếng Việt của `concepts.md` — nếu có chỗ khó hiểu, tham khảo bản tiếng Anh.

# 05 — Khái niệm: Serving một model

> Đọc phần này trước. Sau đó chạy lab trong `README.md`.
> Đã kiểm chứng với tài liệu k8s v1.36 — Deployment `apps/v1`, Service `v1`, Ingress `networking.k8s.io/v1`,
> HPA `autoscaling/v2`, probes (Pod spec `v1`).

---

## 1. "Serving" trong MLOps nghĩa là gì

Training (stage 04) tạo ra một model artifact. **Serving** (phục vụ) nạp artifact đó và
expose nó thành một API để các hệ thống khác có thể lấy prediction. Vòng đời:

```
   train (Job) ──> model.joblib on PVC
                ──> serving Pod loads model at startup
                ──> FastAPI listens on :8000
                ──> POST /predict {features} ──> {class_label, class_name}
```

Stage này là một Deployment (serving Pod phải luôn chạy), không phải Job. Chúng ta thêm:
- **Probes** (liveness + readiness) để k8s biết khi nào Pod khỏe.
- **HPA** (HorizontalPodAutoscaler) để scale replica dựa trên CPU.
- **Ingress** để route HTTP traffic từ ngoài cluster vào Service.

---

## 2. Probes — liveness vs readiness vs startup

Probes báo cho k8s về tình trạng sức khỏe của Pod. Có ba loại:

### Liveness probe
"Pod còn sống không?" Nếu fail, k8s **restart container**.
- Dùng cho: phát hiện deadlock, infinite loop, memory leak khiến app không phản hồi.
- Không dùng cho: kiểm tra model đã load chưa — đó là việc của readiness.
- Endpoint cho app của ta: `GET /health` (trả 200 nếu process còn sống).

### Readiness probe
"Pod sẵn sàng serve traffic chưa?" Nếu fail, k8s **gỡ Pod khỏi endpoints của Service**
(ngừng gửi request tới nó) nhưng KHÔNG restart.
- Dùng cho: "model đã load và tôi có thể serve prediction."
- Quan trọng cho rolling update: Pod mới phải pass readiness trước khi Pod cũ bị gỡ.
- Endpoint cho app của ta: `GET /ready` (trả 200 chỉ sau khi `load_model()` thành công).

### Startup probe
"App đã khởi động xong chưa?" Nếu được set, liveness/readiness sẽ không chạy cho đến khi
startup pass. Hữu ích cho app có khởi động chậm (load model lớn vào memory).
- Ở đây ta không thực sự cần (model iris load <1s), nhưng với LLM (stage 12) thì bắt buộc.

### Manifest

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 3
  periodSeconds: 5
```

- `initialDelaySeconds` — đợi bao lâu trước khi probe lần đầu. Cho app thời gian khởi động.
- `periodSeconds` — probe bao lâu một lần.
- `failureThreshold` — sau nhiều lần fail liên tiếp như vậy, k8s coi probe là failed (mặc định 3).

### Tại sao app của ta có riêng `/health` và `/ready`
- `/health` luôn trả 200 nếu uvicorn đang chạy. Dùng cho liveness (process còn sống).
- `/ready` trả 200 chỉ khi model load thành công. Dùng cho readiness (có thể serve).
- Nếu file model thiếu, `/ready` fail → Pod vẫn nằm ngoài endpoints của Service →
  không traffic tới nó → user không thấy lỗi 500. Đây là hành vi đúng.

---

## 3. HorizontalPodAutoscaler (HPA)

HPA tự động scale số replica dựa trên metrics quan sát được.

### Manifest

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: iris-serve
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: iris-serve
  minReplicas: 2
  maxReplicas: 5
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

- `scaleTargetRef` — scale cái gì (Deployment tên `iris-serve`).
- `minReplicas: 2` — không bao giờ scale dưới 2 (đảm bảo availability).
- `maxReplicas: 5` — không bao giờ scale trên 5 (kiểm soát chi phí).
- `averageUtilization: 70` — nếu CPU trung bình across pods > 70%, scale up; nếu < 70%, scale down.

### Cách HPA hoạt động (vòng lặp)
1. HPA controller poll metrics API mỗi 15s lấy CPU usage của Deployment.
2. Nếu CPU trung bình > 70%, nó tính replica mong muốn: `ceil(current * (current_cpu / target_cpu))`.
3. Nó patch `spec.replicas` của Deployment lên con số đó.
4. ReplicaSet của Deployment tạo/gỡ Pod để khớp.
5. Lặp lại.

### Điều kiện tiên quyết: metrics-server
HPA cần **metrics-server** để cung cấp metrics CPU/memory. kind không kèm nó mặc định.
Ta sẽ cài nó trong lab (chỉ một manifest apply). Thiếu nó, HPA hiện metrics `unknown`
và không bao giờ scale.

---

## 4. Ingress — HTTP routing vào Service

Ingress là cách ở tầng L7 (HTTP) để expose một Service. Ta đã gặp ở stage 00
(cloud-provider-kind xử lý native). Ở đây ta tạo một object Ingress route `serve.local/`
vào Service `iris-serve`.

### Manifest

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: iris-serve
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
  - host: serve.local
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: iris-serve
            port:
              number: 80
```

- `host: serve.local` — hostname mà client sẽ dùng. Bạn cần thêm `127.0.0.1 serve.local`
  (hoặc IP của Ingress) vào `/etc/hosts` trên Mac.
- `pathType: Prefix` — match mọi path bắt đầu bằng `/` (tức là tất cả).
- `backend.service` — route tới Service nào (`iris-serve` port 80).

> **Lưu ý:** cloud-provider-kind gán IP ngoài cho Ingress. Ingress class là
> `cloud-provider-kind` (set tự động). Bạn không cần chỉ định `ingressClassName`
> vì cloud-provider-kind mặc định theo dõi mọi Ingress không có class.

---

## 5. Toàn bộ manifest stack cho serving

```
   Ingress (serve.local) ──routes to──> Service (iris-serve, ClusterIP)
                                         │
                                         ▼
                                    Deployment (iris-serve, replicas: 2)
                                         │ manages
                                    ReplicaSet
                                         │ creates
                                    Pod ── mounts PVC (model-pvc, read-only)
                                    Pod ── runs uvicorn app:app
                                         ▲
                                    HPA watches CPU, scales 2–5
```

Các tài nguyên:
- **PVC** (tạo ở stage 04) — chứa `model.joblib`.
- **Deployment** — 2 replica, mount PVC read-only, chạy `iris-serve:0.1`.
- **Service** — ClusterIP, port 80 → targetPort 8000.
- **Ingress** — route `serve.local` vào Service.
- **HPA** — scale 2–5 dựa trên CPU.

---

## 6. Những gì bạn cần giải thích được sau stage 05

- Khác nhau giữa liveness probe và readiness probe, và tại sao mỗi loại đều quan trọng.
- Tại sao `/ready` trả 500 (model chưa load) lại gỡ Pod khỏi Service.
- Cách HPA quyết định scale up hay down (CPU > target → scale up).
- Tại sao metrics-server bắt buộc với HPA.
- Ingress làm gì mà LoadBalancer Service không làm được (route L7 theo host header).
- Toàn bộ chuỗi: Ingress → Service → Deployment → Pod → PVC → model.

---

## 7. Đọc thêm

- Probes: https://kubernetes.io/docs/concepts/workloads/pods/probes/
- Configure probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
- HPA walkthrough: https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale-walkthrough/
- HPA reference: https://kubernetes.io/docs/reference/kubernetes-api/workload-resources/horizontal-pod-autoscaler-v2/
- Ingress: https://kubernetes.io/docs/concepts/services-networking/ingress/
- metrics-server: https://github.com/kubernetes-sigs/metrics-server