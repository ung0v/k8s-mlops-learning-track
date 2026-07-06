# 01 — Khái niệm: Pod, Deployment, Service, Label

> Bản dịch tiếng Việt của `concepts.md` — nếu có chỗ khó hiểu, tham khảo bản tiếng Anh.
> Đọc phần này trước. Sau đó chạy lab trong `README.md`.
> Đã đối chiếu với tài liệu k8s v1.36 (kubernetes.io/docs/concepts/workloads/pods/,
> /controllers/deployment/, /services-networking/service/) — tất cả API đều stable: `v1`, `apps/v1`.

---

## 1. Pod — đơn vị triển khai nhỏ nhất của k8s

### Pod là gì
Một **Pod** là một nhóm gồm 1+ container mà:
- Chạy trên cùng một node.
- Dùng chung network namespace (cùng IP, cùng port space).
- Dùng chung volumes (lưu trữ).
- Được schedule, khởi động, dừng và chết **cùng nhau**.

Hãy coi Pod như một "logical host" cho ứng dụng của bạn. Nếu hai container phải luôn
co-locate (dùng chung localhost hoặc một file), chúng thuộc về cùng một Pod. Nếu không,
chúng thuộc về các Pod riêng biệt.

### Tại sao lại có Pod (không chỉ là "container")
k8s không chạy container trực tiếp — nó chạy Pod bên trong chứa container. Lớp trung gian này:
- Cho phép co-locate các container hợp tác với nhau (ví dụ. app + log sidecar) với network/volumes dùng chung.
- Cung cấp cho scheduler một đơn vị để đặt (nó đặt Pod, không phải từng container riêng lẻ).
- Cung cấp identity ổn định cho workload bên trong, kể cả khi container bên dưới restart.

### Các fact cần nhớ
- Mỗi Pod nhận một IP duy nhất (thuộc pod CIDR, ví dụ. `10.244.0.12`). Tất cả container trong Pod đều dùng chung IP đó.
- IP của Pod là **ephemeral** — nó thay đổi khi Pod được tạo lại. Không bao giờ hardcode.
- Pod là **mortal** (có thể chết). Chúng không tự self-heal. Nếu một node chết hoặc một container
  crash, chính Pod đó sẽ biến mất. Thứ tạo lại Pod là một controller (ReplicaSet, Job, v.v.) — xem §3.
- Bạn hầu như không bao giờ tạo Pod trực tiếp bằng manifest. Bạn tạo một Deployment, Deployment
  tạo một ReplicaSet, ReplicaSet tạo Pod. Nhưng hiểu Pod manifest là nền tảng.

### Pod manifest, từng trường một

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: nginx
  labels:
    app: nginx
spec:
  containers:
  - name: nginx
    image: nginx:1.27
    ports:
    - containerPort: 80
    resources:
      requests:
        cpu: 100m
        memory: 128Mi
      limits:
        cpu: 200m
        memory: 256Mi
```

- `apiVersion: v1` — core k8s API. Stable ngay từ đầu.
- `kind: Pod` — kiểu resource.
- `metadata.name` — phải duy nhất trong namespace.
- `metadata.labels` — các cặp key/value dùng bởi selector (xem §5). Rất quan trọng cho Service.
- `spec.containers[]` — các container. `image` được pull bởi containerd. `ports.containerPort`
  chỉ mang tính thông tin (nó không thực sự mở port — container mới là thứ mở port); k8s dùng
  nó cho health check và tài liệu hóa.
- `spec.containers[].resources` — **requests** (mức tối thiểu được đảm bảo, dùng cho scheduling)
  so với **limits** (mức tối đa cho phép, được ép bởi cgroups). Trong production luôn phải set.

### Pod lifecycle (rút gọn)
1. Pending → scheduler chọn node → kubelet khởi động container.
2. Running → tiến trình container đang sống.
3. Succeeded / Failed → terminal (chỉ áp dụng cho `restartPolicy: Never/OnFailure`, dùng bởi Job).
4. Với `restartPolicy: Always` mặc định (Deployments), container crash sẽ được kubelet restart.
   Pod object giữ nguyên; bộ đếm container restart tăng lên.

---

## 2. Deployment — "Tôi muốn N replica của Pod này, được rollout và update"

### Deployment là gì
Một **Deployment** là controller ở mức cao hơn. Bạn mô tả:
- Một Pod template (image, port, env, v.v.).
- Số replica mong muốn.
- Chiến lược update (mặc định là RollingUpdate).

Deployment controller tạo một **ReplicaSet**, rồi ReplicaSet tạo ra N Pod. Khi bạn
thay đổi Pod template (ví dụ. tag image mới), Deployment tạo một ReplicaSet **mới**,
scale lên trong khi scale ReplicaSet cũ xuống — đó là rolling update.

### Thứ bậc cần phải nhớ

```
Deployment  ──manages──>  ReplicaSet (v1)  ──manages──>  Pod (× N)
            ──manages──>  ReplicaSet (v2)  ──manages──>  Pod (× N)   ← after a rollout
            ──manages──>  ReplicaSet (v1)  [scaled to 0, kept for rollback]
```

Tại sao giữ ReplicaSet cũ ở 0 replica? **Rollback.** `kubectl rollout undo deployment/nginx`
sẽ scale v1 lên lại và v2 xuống. Lịch sử nằm trong `kubectl rollout history deployment/nginx`.

### Deployment manifest, từng trường một

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-deploy
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nginx
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:1.27
        ports:
        - containerPort: 80
```

- `apiVersion: apps/v1` — workload API. Pod là `v1`; Deployment nằm trong `apps/v1`.
- `spec.replicas` — số Pod mong muốn. ReplicaSet đảm bảo con số này được giữ.
- `spec.selector.matchLabels` — **Deployment sở hữu những Pod nào**. Phải khớp với
  `template.metadata.labels`. Nếu không khớp, Deployment không kiểm soát gì cả. Đây là
  bug phổ biến nhất của người mới.
- `spec.strategy.rollingUpdate`:
  - `maxSurge: 1` — trong lúc rollout, được phép có tối đa 1 Pod **vượt quá** `replicas` tại một thời điểm.
  - `maxUnavailable: 0` — được phép có 0 Pod dưới `replicas` trong lúc rollout (zero-downtime).
  - Nếu bạn có thể chấp nhận mất capacity ngắn hạn nhưng muốn ít Pod tổng cộng hơn, hãy đặt
    `maxUnavailable: 1` thay vào đó.
- `spec.template` — Pod template. Mọi Pod ReplicaSet tạo ra đều được đóng dấu từ đây.

### Lệnh tắt imperative (hữu ích khi test nhanh)
- `kubectl create deployment nginx --image=nginx:1.27 --replicas=3` — sinh ra Deployment
  ngay lúc chạy. Không cần YAML. Tốt cho experimentation; tệ cho GitOps (không có source of truth).
- `kubectl scale deployment/nginx --replicas=5` — scaling kiểu imperative. Kích hoạt reconcile loop.
- `kubectl set image deployment/nginx nginx=nginx:1.28` — bump image kiểu imperative, trigger rolling update.

---

## 3. ReplicaSet — "giữ chính xác N bản sao luôn sống"

Bạn thường không tự viết manifest ReplicaSet — Deployment đã làm thay bạn.
Nhưng bạn nên biết nó làm gì:

- Theo dõi các Pod khớp với selector của nó.
- Đếm chúng.
- Nếu count < N → tạo Pod từ template.
- Nếu count > N → xóa các Pod thừa (chọn ngẫu nhiên, hoặc theo deletion policy).

ReplicaSet chính là thứ nhận biết khi một Pod chết và **tạo lại nó**. Đó là tính năng
"self-healing" của Deployment: không phải phép thuật, mà là ReplicaSet đếm Pod mỗi vài
giây và reconcile.

Bạn có thể xem ReplicaSet bằng `kubectl get rs`. Deployment sở hữu chúng; tự xóa một
ReplicaSet bằng tay cũng chỉ khiến Deployment tạo lại nó. Đừng chống lại nó.

---

## 4. Service — một tên + IP ổn định, route tới một tập Pod

### Vấn đề Service giải quyết
IP của Pod thay đổi mỗi lần restart. Các pod khác không thể giữ kết nối đến nó.
Một **Service** là một IP + DNS name ổn định, load-balance trên các Pod khớp.

```
   caller ──> Service (stable IP, DNS name) ──> Pod1 (10.244.0.5)
                                          └─> Pod2 (10.244.0.6)
                                          └─> Pod3 (10.244.0.7)
```

Pod sinh ra rồi biến mất; IP của Service giữ nguyên. Bên trong, kube-proxy cập nhật
luật iptables/IPVS trên mỗi node sao cho gói tin gửi tới Service IP sẽ được DNAT tới
một Pod đang khỏe.

### Service manifest, từng trường một

```yaml
apiVersion: v1
kind: Service
metadata:
  name: nginx-svc
spec:
  type: ClusterIP
  selector:
    app: nginx
  ports:
  - port: 80
    targetPort: 80
    protocol: TCP
```

- `spec.type: ClusterIP` — chỉ expose Service bên trong cluster. Đây là mặc định.
- `spec.selector` — chọn Pod nào Service này route tới. **Cùng label với Pod template**.
  Đây là cách Service và Pod kết nối với nhau: bằng label, không phải bằng tên.
- `spec.ports[].port` — port mà Service lắng nghe (port mà caller dùng).
- `spec.ports[].targetPort` — port trên container của Pod (port mà app lắng nghe).
  Có thể là số hoặc một named port.

### Bốn kiểu Service (hãy nhớ bảng này)

| Type           | Truy cập được từ          | Cách hoạt                                                          |
|----------------|---------------------------|---------------------------------------------------------------------|
| **ClusterIP**  | Chỉ bên trong cluster     | Nhận một virtual IP từ service CIDR. kube-proxy lập trình rules.    |
| **NodePort**   | Bên ngoài, qua IP mọi node | Mở một port trong khoảng 30000–32767 trên mỗi node. Dựng trên ClusterIP.|
| **LoadBalancer**| Bên ngoài, qua cloud LB   | Cloud provider cấp một LB trỏ tới NodePort. External IP được gán.   |
| **ExternalName** | Bên trong, nhưng là DNS alias | Trả về CNAME tới một DNS name bên ngoài (ví dụ. `mydb.rds.amazonaws.com`). Không proxy. |

Bạn hầu như luôn bắt đầu bằng `ClusterIP` và chỉ expose những thứ thực sự cần public.
Cho ứng dụng HTTP trong cluster kind của chúng ta, **Ingress** (stage 00) là cách
production-grade để expose nhiều Service qua cùng một external IP.

### DNS — tại sao Service có tên, không chỉ có IP
CoreDNS (chạy trong `kube-system`) tạo một DNS record cho mỗi Service:
`<service-name>.<namespace>.svc.cluster.local`. Pod trong cùng namespace có thể dùng
luôn `<service-name>` — tên này resolve ra ClusterIP của Service. Đây là cách một Pod
gọi một Pod khác: bằng tên Service, không bao giờ bằng IP của Pod.

Ví dụ: một app FastAPI gọi Redis sẽ dùng `redis-svc:6379`, chứ không phải `10.244.0.12:6379`.

---

## 5. Label và Selector — mô liên kết của k8s

### Label là gì
Label là các cặp key/value gắn vào **bất kỳ** object k8s nào. Chúng dùng để **nhận diện và
gom nhóm**, không phải để cấu hình (dùng annotation cho mục đích đó).

```yaml
metadata:
  labels:
    app: nginx
    tier: frontend
    env: prod
```

### Selector là gì
Selector là các truy vấn trên label. Có hai kiểu:

- **Equality-based**: `app=nginx`, `env!=dev`
- **Set-based**: `app in (nginx, api)`, `tier notin (debug)`

Được dùng ở ba nơi trọng yếu:
1. **Deployment.spec.selector** — Pod nào nó sở hữu.
2. **Service.spec.selector** — Pod nào nó route tới.
3. **`kubectl get pods -l app=nginx`** — lọc trên CLI.

### Mẫu kết nối (hãy vẽ ra)

```
   Deployment         Service
   selector:            selector:
     app: nginx           app: nginx
        │                    │
        │ creates Pods with  │ selects Pods with
        │   label app=nginx  │   label app=nginx
        ▼                    ▼
        ┌──────────────────────┐
        │  Pod (app=nginx)     │
        │  Pod (app=nginx)     │
        │  Pod (app=nginx)     │
        └──────────────────────┘
```

Deployment và Service đều tham chiếu tới **cùng một label** (`app: nginx`). Deployment
*ghi* label lên Pod (thông qua template của nó). Service *đọc* label để tìm Pod cần route tới.
Chúng không bao giờ tham chiếu trực tiếp tới nhau. Sự tách rời (decoupling) này chính là
cốt lõi — bạn có thể thay Deployment, scale, roll, và Service vẫn hoạt động miễn là còn
Pod khớp.

### Label khuyến nghị (theo convention k8s)
Tài liệu k8s khuyến nghị một tập hợp label phổ biến (xem `kubectl explain` cho bất kỳ resource):
- `app` — tên ứng dụng
- `tier` — tầng kiến trúc (frontend/backend/cache)
- `env` — môi trường (dev/staging/prod)
- `version` — phiên bản image, dùng cho canary/rollback

Về sau chúng ta chủ yếu dùng `app` và một label tùy chỉnh `stage` (cho MLflow model stage).

---

## 6. Namespace — xem lại

Chúng ta đã gặp namespace ở stage 00. Tóm tắt nhanh cho stage này:

- Namespace là ranh giới scope cho tên. `nginx-deploy` trong `default` và `nginx-deploy`
  trong `mlflow` là hai Deployment khác nhau.
- Resource trong một namespace có thể tham chiếu Service ở namespace khác bằng DNS name đầy đủ:
  `redis-svc.mlflow.svc.cluster.local`.
- Namespace được tạo bằng `kubectl create ns <name>` hoặc bằng manifest.
- Hầu hết lệnh `kubectl` mặc định chạy trong namespace `default` trừ khi bạn truyền `-n <ns>`.

Trong stage 01 chúng ta giữ mọi thứ trong `default` để câu lệnh ngắn gọn. Các stage sau sẽ
chuyển sang namespace riêng (`mlflow`, `kubeflow`, v.v.) để phản ánh production hygiene.

---

## 7. Mô hình tâm lý gắn kết mọi thứ

Khi bạn `kubectl apply -f deployment.yaml` cho một Deployment 3-replica nginx + một Service
ClusterIP, đây là toàn bộ chuỗi:

1. **Bạn** → API server: "lưu Deployment này lại"
2. **Deployment controller** thấy nó → tạo một **ReplicaSet** (revision 1)
3. **ReplicaSet controller** thấy ReplicaSet → cần 3 Pod → tạo 3 **Pod object**
4. **Scheduler** thấy 3 Pod chưa được schedule → gán mỗi Pod vào một node (ở đây: tất cả vào
   `kind-control-plane`, node duy nhất của ta) → ghi `nodeName`
5. **Kubelet** trên node thấy 3 Pod mới được gán cho mình → gọi containerd → pull
   `nginx:1.27` → khởi động 3 container → báo cáo Running về lại API server
6. **Bạn** → `kubectl apply -f service.yaml` → API server lưu Service
7. **Endpoints controller** (và EndpointSlice controller) thấy selector của Service
   (`app=nginx`) → tra cứu Pod khớp → ghi IP của chúng vào một EndpointSlice
8. **kube-proxy** trên mỗi node thấy EndpointSlice → lập trình luật iptables/IPVS →
   từ giờ, gửi gói tin tới ClusterIP của Service sẽ DNAT tới một trong 3 IP của Pod
9. **CoreDNS** thấy Service mới → thêm một A record `<svc>.<ns>.svc.cluster.local`
   trỏ tới ClusterIP
10. Bất kỳ Pod nào trong cluster giờ có thể `curl http://nginx-svc` và nhận phản hồi
    từ một trong 3 Pod nginx, load-balance round-robin

Mỗi bước là một controller riêng biệt theo dõi etcd và phản ứng. Không có "main loop"
nào chạy toàn bộ show — đó là lý do k8s vừa resilient vừa mở rộng được.

---

## 8. Những gì bạn cần giải thích được sau stage 01

- Pod là gì và tại sao nó tồn tại (không chỉ là "container wrapper").
- Thứ bậc Deployment → ReplicaSet → Pod và mỗi lớp thêm gì.
- Tại sao IP của Pod là ephemeral và Service xử lý điều đó ra sao.
- Bốn kiểu Service và khi nào dùng kiểu nào.
- Cách Label + Selector kết nối Deployment, Pod và Service (vẽ sơ đồ).
- `kubectl apply`, `kubectl scale`, `kubectl rollout` làm gì với reconcile loop.
- Tại sao DNS hoạt động bên trong cluster (`nginx-svc` resolve ra ClusterIP).
- Toàn bộ chuỗi từ `apply` tới "curl chạy được" (§7).

---

## 9. Tài liệu đọc thêm (chính thức)

- Pods: https://kubernetes.io/docs/concepts/workloads/pods/
- Pod lifecycle: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
- Deployment: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/
- ReplicaSet: https://kubernetes.io/docs/concepts/workloads/controllers/replicaset/
- Service: https://kubernetes.io/docs/concepts/services-networking/service/
- Labels and Selectors: https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/
- DNS for Services: https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/
- Run a stateless app with a Deployment: https://kubernetes.io/docs/tasks/run-application/run-stateless-application-deployment/
- Connect a frontend to a backend using Services: https://kubernetes.io/docs/tasks/access-application-cluster/connecting-frontend-backend/