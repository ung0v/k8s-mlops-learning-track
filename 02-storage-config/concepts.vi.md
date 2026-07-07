# 02 — Khái niệm: Storage, Config, và StatefulSet

> Bản dịch tiếng Việt của `concepts.md` — nếu có chỗ khó hiểu, tham khảo bản tiếng Anh.
> Đọc file này trước. Sau đó chạy lab trong `README.md`.
> Đã kiểm chứng với tài liệu k8s v1.36 — tất cả API đều ổn định: PV/PVC `v1`, StatefulSet `apps/v1`,
> ConfigMap `v1`, Secret `v1`, init container (Pod spec `v1`).

---

## 1. Tại sao Pod cần storage và config

Các Pod nginx ở stage 01 là stateless: không có dữ liệu nào quan trọng, không có config nào thay đổi. Ứng dụng thực tế cần:

- **Dữ liệu persistent** — một database ghi file phải tồn tại qua các lần Pod restart.
- **Configuration** — ứng dụng đọc file config hoặc env var (DB host, log level, model path).
- **Secrets** — mật khẩu, API key, TLS cert — không được để trong plaintext YAML hoặc env var.

Kubernetes cung cấp ba loại resource + một workload controller cho các ứng dụng stateful:
- **PersistentVolume (PV)** + **PersistentVolumeClaim (PVC)** — storage bền vững.
- **ConfigMap** — config không nhạy cảm, được inject dưới dạng env var hoặc file.
- **Secret** — dữ liệu nhạy cảm, cùng cơ chế inject, được mã hóa base64 (không mã hóa mặc định).
- **StatefulSet** — controller cấp cho mỗi Pod một identity ổn định + volume riêng.

---

## 2. Volume vs PersistentVolume — hai khái niệm storage

### Volume (ephemeral, gắn với vòng đời Pod)
Một **Volume** được định nghĩa inline trong Pod spec. Nó tồn tại miễn là Pod còn sống. Các loại phổ biến:
- `emptyDir` — vùng nhớ tạm trên node. Bị xóa khi Pod chết. Phù hợp để chia sẻ dữ liệu giữa các container trong cùng Pod.
- `hostPath` — mount file/thư mục từ host node. Nguy hiểm trong prod (gắn Pod vào node), hữu ích để debug.
- `configMap` / `secret` — chiếu dữ liệu ConfigMap/Secret thành file.

```yaml
spec:
  containers:
  - name: app
    volumeMounts:
    - name: data
      mountPath: /scratch
  volumes:
  - name: data
    emptyDir: {}
```

### PersistentVolume (bền vững, độc lập với Pod)
Một **PersistentVolume (PV)** là resource storage ở mức cluster. Nó sống lâu hơn bất kỳ Pod nào.
Một **PersistentVolumeClaim (PVC)** là yêu cầu storage của người dùng: "tôi muốn 5Gi, ReadWriteOnce".

Hãy coi như mô hình cloud computing:
- **PV** = ổ đĩa thực (được admin cấp hoặc tự động bởi StorageClass).
- **PVC** = vé yêu cầu ghi "cho tôi một ổ đĩa khớp với các yêu cầu này".
- Pod mount **PVC**, không mount PV trực tiếp.

```
   admin/cloud ─creates─> PV (real disk)
                         ↑ bound to
   user ─creates─> PVC (claim: 5Gi RWO)
                    ↑ mounted by
   Pod spec ─references─> PVC
```

### Access mode (học thuộc)
- `ReadWriteOnce` (RWO) — một node có thể đọc/ghi. Phổ biến nhất cho kind single-node.
- `ReadOnlyMany` (ROX) — nhiều node có thể đọc. Tốt cho dữ liệu dùng chung chỉ đọc.
- `ReadWriteMany` (RWX) — nhiều node có thể đọc/ghi. Cần NFS hoặc distributed FS.
- `ReadWriteOncePod` (RWOP) — chỉ một **Pod** có thể mount (mạnh hơn RWO).

> **Lưu ý:** kind đi kèm `standard` StorageClass (provisioner `rancher.io/local-path`)
> cấp PV dựa trên hostPath động. Nó dùng binding `WaitForFirstConsumer`
> (trì hoãn binding cho đến khi Pod được schedule, để volume nằm đúng node). Nếu bạn
> không chỉ định `storageClassName`, k8s dùng default (là `standard` trong kind).

### Reclaim policy
- `Retain` — khi PVC bị xóa, PV vẫn còn cùng dữ liệu. Dọn dẹp thủ công.
- `Delete` (mặc định cho dynamic provisioning) — khi PVC bị xóa, PV + dữ liệu bị xóa.

### Manifest PVC

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data-pvc
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: local-path
  resources:
    requests:
      storage: 1Gi
```

Pod tham chiếu đến nó theo tên:

```yaml
spec:
  containers:
  - name: app
    volumeMounts:
    - name: data
      mountPath: /data
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: data-pvc
```

---

## 3. ConfigMap — inject config mà không cần rebuild image

Một **ConfigMap** là key-value store cho config không nhạy cảm. Có ba cách inject:

### (a) Dưới dạng environment variable
```yaml
spec:
  containers:
  - name: app
    env:
    - name: LOG_LEVEL
      valueFrom:
        configMapKeyRef:
          name: app-config
          key: log_level
```

### (b) Dưới dạng một env block (envFrom)
```yaml
spec:
  containers:
  - name: app
    envFrom:
    - configMapRef:
        name: app-config
```
Tất cả key trở thành env var. Tiện nhưng không kiểm soát được tên.

### (c) Dưới dạng file mount trong volume
```yaml
spec:
  containers:
  - name: app
    volumeMounts:
    - name: config
      mountPath: /etc/config
      readOnly: true
  volumes:
  - name: config
    configMap:
      name: app-config
```
Mỗi key trở thành một file; nội dung file là giá trị của key. Tốt nhất cho config file
mà ứng dụng đọc (nginx.conf, application.yml). Các cập nhật ConfigMap lan truyền tới
file mount trong ~1 phút (kubelet sync) — nhưng inject env var thì cần restart Pod.

### Manifest ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  log_level: "info"
  app.properties: |
    color.good=purple
    color.bad=yellow
    allow.textmode=true
```

Hai key: `log_level` (một string) và `app.properties` (một string nhiều dòng trở thành một file).

---

## 4. Secret — giống ConfigMap nhưng dành cho dữ liệu nhạy cảm

Một **Secret** giống hệt ConfigMap về cấu trúc nhưng:
- Giá trị được mã hóa base64 (để dữ liệu binary như TLS cert hoạt động).
- Không được mã hóa at-rest mặc định (cần bật encryption-at-rest trong API server cho điều đó).
- Mặc định mount trong tmpfs (RAM), không ghi ra disk trên node.
- Có thể bị giới hạn bởi RBAC tách biệt với ConfigMap.

> **Cẩn thận:** base64 KHÔNG phải là mã hóa. Bất kỳ ai có `kubectl get secret -o yaml` đều có thể decode.
> Quản lý secret thực sự cần external secret store (Vault, AWS Secrets Manager, Sealed Secrets, v.v.).

### Tạo Secret
Cách sạch nhất là tạo từ giá trị literal:

```bash
kubectl create secret generic db-secret \
  --from-literal=username=admin \
  --from-literal=password='s3cr3t!'
```

Hoặc từ manifest (bạn phải tự mã hóa base64 — `echo -n 's3cr3t!' | base64`):

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: db-secret
type: Opaque
data:
  username: YWRtaW4=          # base64('admin')
  password: czNjcjN0IQ==      # base64('s3cr3t!')
```

### Inject secret
Cùng ba cách như ConfigMap: `env` + `secretKeyRef`, `envFrom` + `secretRef`, hoặc dưới dạng volume.

---

## 5. StatefulSet — công cụ đúng cho workload stateful, có identity

### Tại sao không dùng Deployment cho database?
Một Deployment tạo các Pod có thể thay thế: `nginx-7c4b-abc`, `nginx-7c4b-def`, ...
Không Pod nào có identity ổn định. Khi một Pod chết, một Pod mới với tên và IP mới thay thế.
Điều đó ổn cho ứng dụng stateless, nhưng tệ cho:
- **Database** — mỗi replica cần dữ liệu riêng, và một tên ổn định để peer tìm thấy nó.
- **Hệ thống phân tán** — ZooKeeper, etcd, Kafka: mỗi node có identity, gia nhập cluster theo tên.

### StatefulSet cho bạn gì
- **Tên Pod ổn định, đoán trước được**: `web-0`, `web-1`, `web-2` (không phải hash ngẫu nhiên).
- **DNS ổn định**: mỗi Pod có một DNS record `web-0.web-svc.default.svc.cluster.local`.
- **Storage ổn định**: mỗi Pod có PVC riêng (qua `volumeClaimTemplates`), và khi Pod được
  reschedule, nó gắn lại cùng PVC — dữ liệu theo identity, không theo Pod.
- **Khởi động và tắt theo thứ tự**: Pod được tạo theo thứ tự 0→1→2, xóa theo thứ tự ngược 2→1→0.
  Hữu ích khi Pod 1 cần Pod 0 ready trước (vd primary rồi mới replica).

### StatefulSet vs Deployment (học thuộc bảng này)

| Thuộc tính          | Deployment                | StatefulSet                          |
|---------------------|---------------------------|--------------------------------------|
| Tên Pod             | `<deploy>-<rs>-<rand>`    | `<statefulset>-<ordinal>`            |
| Pod identity        | Có thể thay thế           | Mỗi Pod có tên ổn định + DNS         |
| Storage             | PVC dùng chung (tất cả replica) | Một PVC mỗi replica (volumeClaimTemplates) |
| Thứ tự khởi động    | Song song                  | Tuần tự (0,1,2...)                   |
| Network identity    | Service load-balance      | Mỗi Pod có DNS A record riêng        |
| Use case            | Web app stateless         | Database, hệ thống phân tán          |

### Manifest StatefulSet

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: web
spec:
  serviceName: web-svc          # the headless Service that gives Pods DNS names
  replicas: 3
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
      - name: nginx
        image: nginx:1.27
        ports:
        - containerPort: 80
        volumeMounts:
        - name: www
          mountPath: /usr/share/nginx/html
  volumeClaimTemplates:        # each Pod gets its own PVC from this template
  - metadata:
      name: www
    spec:
      accessModes: [ReadWriteOnce]
      storageClassName: local-path
      resources:
        requests:
          storage: 100Mi
```

Hai điểm khác với Deployment:
- `serviceName: web-svc` — tên **headless Service** (clusterIP: None) đứng sau StatefulSet này.
  Headless Service không load-balance — nó trả trực tiếp IP của Pod, để client có thể
  địa chỉ hóa `web-0` hoặc `web-1` theo tên.
- `volumeClaimTemplates` — mỗi replica có PVC riêng: `www-web-0`, `www-web-1`, `www-web-2`.
  Khi `web-1` được reschedule sang node khác, nó gắn lại `www-web-1` — cùng dữ liệu.

### Headless Service (bạn đồng hành của StatefulSet)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: web-svc
spec:
  clusterIP: None          # this is what makes it "headless"
  selector:
    app: web
  ports:
  - port: 80
```

`clusterIP: None` báo k8s: "đừng cấp IP ảo và đừng load-balance. Chỉ cho tôi
DNS A record cho mỗi Pod." Bây giờ `web-0.web-svc` resolve tới IP của `web-0`, và `web-svc` resolve
tới cả ba (round-robin ở mức DNS).

---

## 6. Init container — chạy thứ gì đó trước khi main app khởi động

Một **init container** chạy đến khi hoàn tất trước khi main container khởi động. Các use case:
- Chuẩn bị trước volume (tải model, sinh config).
- Đợi dependency ready (vd đợi port của DB Pod phản hồi).
- Chạy setup script với công cụ/quyền hạn khác main container.

```yaml
spec:
  initContainers:
  - name: init
    image: busybox:1.36
    command: ['sh', '-c', 'echo "hello from init" > /data/index.html']
    volumeMounts:
    - name: www
      mountPath: /data
  containers:
  - name: nginx
    image: nginx:1.27
    volumeMounts:
    - name: www
      mountPath: /usr/share/nginx/html
  volumes:
  - name: www
    emptyDir: {}
```

Init container ghi `index.html` vào volume `www` dùng chung. Container nginx chính
phục vụ nó. Init container chạy **tuần tự** và phải tất cả thành công trước khi main container khởi động.

---

## 7. Mô hình tinh thần gắn kết tất cả lại

Khi bạn `kubectl apply -f statefulset.yaml` với `volumeClaimTemplates`:

1. **StatefulSet controller** tạo Pod `web-0` trước.
2. **PVC controller** thấy `volumeClaimTemplates`, tạo PVC `www-web-0`.
3. **StorageClass** (`local-path`) cấp PV (một thư mục trên node kind) và bind PVC.
4. **Scheduler** đặt `web-0` lên một node.
5. **Kubelet** mount PV vào `web-0`, khởi động nginx.
6. Khi `web-0` Ready, controller tạo `web-1`. Cùng flow tạo PVC.
7. Rồi `web-2`. (Tuần tự, không song song — đó là semantics của StatefulSet.)
8. **Headless Service** `web-svc` cấp cho mỗi Pod một DNS A record.
9. Nếu Pod `web-1` chết, StatefulSet tạo Pod **mới** tên `web-1` (cùng tên!),
   gắn lại **cùng** PVC `www-web-1`, và dữ liệu quay lại.

So với Deployment: Pod chết được thay bằng Pod tên mới, không storage cụ thể,
không identity cụ thể. Đó là lý do Deployment dành cho stateless, StatefulSet dành cho stateful.

---

## 8. Những gì bạn có thể giải thích sau stage 02

- Khác biệt giữa Volume (ephemeral) và PersistentVolume (bền vững).
- PVC là gì và Pod tham chiếu nó ra sao.
- Ba cách inject ConfigMap vào Pod (env, envFrom, volume).
- Tại sao Secret tồn tại tách biệt với ConfigMap (base64, tmpfs, RBAC).
- Tại sao base64 không phải mã hóa (và bạn cần gì cho quản lý secret thực sự).
- Khi nào dùng StatefulSet vs Deployment.
- Headless Service là gì và tại sao StatefulSet cần nó.
- Init container làm gì và một use case thực tế cho nó.
- Tại sao xóa Pod StatefulSet tạo Pod mới với **cùng tên** (identity ổn định).

---

## 9. Đọc thêm (tài liệu chính thức)

- Persistent Volumes: https://kubernetes.io/docs/concepts/storage/persistent-volumes/
- Storage Classes: https://kubernetes.io/docs/concepts/storage/storage-classes/
- Dynamic volume provisioning: https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/
- Configure a Pod to use a PersistentVolume: https://kubernetes.io/docs/tasks/configure-pod-container/configure-volume-storage/
- StatefulSets: https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/
- StatefulSet basics tutorial: https://kubernetes.io/docs/tutorials/stateful-application/basic-stateful-set/
- ConfigMaps: https://kubernetes.io/docs/concepts/configuration/configmap/
- Configure a Pod to use a ConfigMap: https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/
- Secrets: https://kubernetes.io/docs/concepts/configuration/secret/
- Init containers: https://kubernetes.io/docs/concepts/workloads/pods/init-containers/
- Volumes (all types): https://kubernetes.io/docs/concepts/storage/volumes/