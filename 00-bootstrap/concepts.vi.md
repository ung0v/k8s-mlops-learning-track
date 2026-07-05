# 00 — Khái niệm: Kiến trúc Kubernetes & những kiến thức nền tảng về cluster

> Đọc file này **trước khi** chạy các lệnh trong `README.md`. Đây là phần "tại sao" và "là gì".
> README là phần "làm thế nào". Cả hai cùng tạo thành một bài học.
> (Bản dịch tiếng Việt của `concepts.md` — nếu có chỗ nào khó hiểu, tham khảo bản tiếng Anh.)

---

## 1. Kubernetes giải quyết vấn đề gì?

Hãy tưởng tượng bạn có một app Python Flask. Trên laptop bạn chạy `python app.py`.
Trong môi trường production bạn cần:

- **Nhiều bản sao** chạy cùng lúc (một bản chết không làm sập trang).
- **Tự động khởi động lại** khi một bản crash.
- **Tự scale** lên/xuống theo tải.
- **Rolling update** (lên phiên bản mới mà không downtime).
- **Networking** giữa các bản sao và ra ngoài thế giới.
- **Chạy cùng app trên 50 máy** mà không cần SSH vào từng máy.

Bạn *có thể* viết bash scripts + systemd units + cấu hình load balancer để làm hết việc này.
Hoặc dùng một hệ thống được thiết kế đúng cho việc đó: **Kubernetes (k8s)**.

Kubernetes là một **container orchestrator** (bộ điều phối container): nó quyết định
container nào chạy ở đâu, giữ chúng khỏe, network cho chúng, và scale chúng — một cách
**khai báo (declarative)**. Bạn mô tả *trạng thái mong muốn* ("tôi muốn 3 pod nginx");
k8s liên tục làm cho thực tế khớp với mong muốn đó.

---

## 2. Mô hình khai báo (declarative) — ý tưởng quan trọng nhất

Kubernetes là **declarative**, không phải imperative (mệnh lệnh).

| Kiểu         | Ví dụ                                                | Ai hành động             |
|--------------|------------------------------------------------------|--------------------------|
| Imperative   | "Khởi động nginx trên node-2 ngay"                   | Bạn, thủ công            |
| Declarative  | "Tôi muốn 3 pod nginx luôn chạy"                     | k8s, liên tục            |

Bạn viết YAML mô tả **trạng thái mong muốn** và đưa cho k8s API. Một controller
bên trong k8s nhận thấy sự khác biệt giữa mong muốn và thực tế, và **điều hòa
(reconcile)** — tạo pod, xóa pod thừa, khởi động lại pod chết. Nếu một node cháy,
k8s nhận thấy các pod biến mất và lên lịch lại ở chỗ khác. Bạn không cần ra lệnh.

Vòng lặp điều hòa (reconcile loop) này là trái tim của k8s. Mọi resource (Pod,
Deployment, Service, Ingress, Job, ...) đều được quản lý theo cách này. Hãy ghi nhớ
mô hình này:

```
   bạn ──apply YAML──> API server ──ghi vào──> etcd
                                            │
                                            ▼
                        controller theo dõi etcd
                                            │
                          nhận thấy khác biệt với thực tế
                                            │
                            hành động (tạo/xóa pod)
                                            │
                                  thực tế thay đổi
                                            │
                          controller lại theo dõi, lặp lại
```

---

## 3. Kiến trúc cluster: control plane vs worker node

Một k8s **cluster** là tập hợp các máy chạy container của bạn. Chia thành hai vai trò:

### Control plane (bộ "não")
- **API server** — cửa trước. Mọi thứ (`kubectl`, controller, kubelet) đều nói chuyện
  với nó qua HTTPS. Nó xác thực request và ghi vào etcd.
- **etcd** — một key-value store phân tán. **Nguồn sự thật duy nhất** cho trạng thái
  cluster. Nếu etcd mất, cluster bị mất trí nhớ.
- **scheduler** — quyết định *node nào* một Pod mới sẽ chạy (dựa trên tài nguyên,
  label, taint).
- **controller manager** — chạy các reconcile loop cho resource built-in (ReplicaSet,
  Deployment, Job, Service, ...).
- **cloud-controller-manager** — cầu nối tới cloud provider (AWS/GCP/Azure) và trong
  trường hợp của chúng ta là **cloud-provider-kind**. Nó là thứ yêu cầu "cloud" cấp
  một LoadBalancer.

### Worker node (cơ "bắp")
- **kubelet** — agent trên mỗi node. Nói chuyện với API server, khởi động/dừng
  container thông qua container runtime, báo cáo trạng thái.
- **kube-proxy** — lập trình rule iptables/IPVS trên node để Service điều phối traffic
  tới đúng Pod.
- **container runtime** — thực sự chạy container. Trong kind đó là `containerd` nằm
  bên trong container node kind. Trên một Linux box thật thì có thể là `containerd`
  hoặc `CRI-O`.

### kind đóng vai trò gì
kind chạy **toàn bộ cluster** (control plane + worker) bên trong một Docker container
duy nhất tên `kind-control-plane`. Bên trong container đó: etcd, API server, kubelet,
containerd, kube-proxy — đều chạy như các process. Đó là lý do bạn có thể "xóa cluster"
bằng một lệnh: `kind delete cluster` chỉ gỡ Docker container. Cluster của chúng ta
single-node, nên control plane và worker cùng nằm trên một node.

```
   Mac của bạn
   └── Docker
       └── container: kind-control-plane
           ├── etcd
           ├── kube-apiserver
           ├── kube-controller-manager
           ├── kube-scheduler
           ├── kubelet
           ├── kube-proxy
           └── containerd ── chạy pod app của bạn (cũng là nested container)
```

---

## 4. API server là con đường duy nhất vào

Mọi tác nhân trong hệ thống (bạn, controller, kubelet, pod khác) đều nói chuyện với
cùng một endpoint: **API server**, qua HTTPS. Không ai đọc etcd trực tiếp ngoài API
server. Điều này có nghĩa:

- `kubectl get pods` → API server → etcd → trả về.
- Một controller tạo Pod → API server → etcd → scheduler thấy → kubelet trên node
  được thông báo → containerd khởi động container.
- `kubectl apply -f foo.yaml` → chỉ gửi YAML tới API server; controller làm phần còn lại.

`kubectl` về cơ bản là một HTTP client hào nhoáng. Bạn có thể `curl` thẳng API server
(với client cert) và nhận kết quả tương tự. Đó là lý do `kubectl config use-context`
quan trọng — nó chọn API server + credential nào sẽ dùng.

---

## 5. Các loại resource cốt lõi bạn sẽ gặp

Đây là các "danh từ" của k8s. Mỗi stage giới thiệu resource mới; đây là nền tảng:

| Resource        | Là gì                                                | Quản lý                  |
|-----------------|------------------------------------------------------|--------------------------|
| **Pod**         | 1+ container, chia sẻ network, cùng vị trí           | workload thực tế         |
| **ReplicaSet**  | "Luôn giữ N bản sao của Pod này chạy"                | Pod                      |
| **Deployment**  | "Triển khai phiên bản X của ReplicaSet, rolling update" | ReplicaSet             |
| **Service**     | DNS name + IP ổn định, route tới tập Pod             | Pod (qua selector)       |
| **Ingress**     | routing HTTP(L7) từ ngoài cluster vào Service        | Service                  |
| **ConfigMap**   | dữ liệu config (không nhạy cảm) bơmvào Pod           | -                        |
| **Secret**      | dữ liệu nhạy cảm, base64-encoded, bơmvào Pod         | -                        |
| **Volume/PV/PVC** | storage cố định                                    | -                        |
| **Namespace**   | nhóm logic của resource (multi-tenancy)              | tất cả ở trên            |

Thứ bậc: **Deployment → ReplicaSet → Pod → container**. Hầu như bạn không bao giờ
tạo Pod trực tiếp; bạn tạo Deployment và để k8s tạo Pod.

---

## 6. Service: networking bên trong cluster hoạt động thế nào

IP của Pod thay đổi mỗi lần restart. Nên bạn không thể dựa vào Pod IP. Một **Service**
cho bạn **IP + DNS name ổn định** load-balanced qua các Pod khớp.

Ba kiểu Service cần biết ngay:

- **ClusterIP** (mặc định) — chỉ reachable *bên trong* cluster. Dùng cho service
  nội bộ (vd: database mà app gọi tới).
- **NodePort** — mở một port (30000–32767) trên **mọi node's** IP. Reachable từ
  ngoài cluster nhưng trên port cao. Là building block cho LoadBalancer.
- **LoadBalancer** — yêu cầu cloud provider (hoặc cloud-provider-kind) cấp một load
  balancer thật trỏ vào Service. External IP được gán. Đây là cách production-grade
  để expose service.

### Ingress vs LoadBalancer Service
Cả hai đều expose app ra ngoài cluster, nhưng ở các layer OSI khác nhau:

- **LoadBalancer Service** — L4 (TCP). Một Service = một external IP = một port.
  Muốn 10 service? Cần 10 IP. Tốn kém.
- **Ingress** — L7 (HTTP/HTTPS). Một external IP có thể route tới nhiều Service dựa
  trên host header (`mlflow.local` → MLflow, `api.local` → API). Cần một Ingress
  controller thực sự nhận traffic. Trong cluster chúng ta, **cloud-provider-kind**
  đóng vai trò vừa là Ingress controller *vừa* là LoadBalancer provider.

Quy tắc: app HTTP → Ingress. TCP/non-HTTP → LoadBalancer Service.

---

## 7. cloud-provider-kind là gì và tại sao tồn tại?

Trên cloud thật (AWS/GCP/Azure), khi bạn tạo `Service: type: LoadBalancer`,
cloud-controller-manager của k8s gọi cloud API → AWS cấp ELB → traffic chạy.
Trên cluster dev local (kind, minikube, k3d) thì không có cloud. Nên trước đây:

- Cách cũ: cài `ingress-nginx`, hack `extraPortMappings` để port 80 trên container
  node kind maps tới port 80 trên Mac. Hoạt động nhưng rối rắm.
- Cách mới (kind v0.27+): **cloud-provider-kind** — một binary "cloud giả" chạy trên
  host. Nó theo dõi LoadBalancer Service và Ingress, và tạo một **Docker container**
  đóng vai load balancer. Container có Docker bridge IP (vd `192.168.97.3`) reachable
  từ Mac, và forward traffic tới đúng node kind. Đó là lý do Ingress example của chúng
  ta nhận IP `192.168.97.3` — đó là một Docker container, không phải pod.

```
   curl → 192.168.97.3 (LB container) → kind-control-plane container → Service → Pod
```

Cách này mô phỏng cách cloud thật hoạt động nhưng ở local. Đó là lý do chúng ta chạy
với `sudo`: nó cần quản lý Docker container và host networking.

---

## 8. kind-config.yaml — các trường đó nghĩa là gì

```yaml
apiVersion: kind.x-k8s.io/v1alpha4
kind: Cluster
name: kind
nodes:
- role: control-plane
  image: kindest/node:v1.36.1
  kubeadmConfigPatches:
  - |
    kind: InitConfiguration
    nodeRegistration:
      kubeletExtraArgs:
        node-labels: "ingress-ready=true"
```

- `kind: Cluster` — đây là config đặc thù kind, **không phải** manifest k8s. Bạn đưa
  cho binary `kind`, không phải `kubectl`.
- `nodes[].role: control-plane` — một node, vai trò control-plane (cluster multi-node
  thì bạn thêm dòng `- role: worker`).
- `image: kindest/node:v1.36.1` — Docker image kind dùng làm "node". Nó bundle
  kubeadm + kubelet + containerd + tất cả binary k8s cho phiên bản đó. Pin image =
  pin phiên bản k8s.
- `kubeadmConfigPatches` — patch thô đưa vào `kubeadm` (công cụ bootstrap cluster k8s
  bên trong node). Ở đây ta thêm label `ingress-ready=true` cho node — một hint cũ mà
  một số ingress controller kiểm tra. cloud-provider-kind không thực sự cần nó; ta
  giữ cho tương thích với guide cũ.

---

## 9. `kubectl` — client của API

`kubectl` là CLI client chính thức cho API server. Mô hình tâm lý:

```
kubectl <verb> <resource-type> [name] [flags]
        │      │                │
        │      │                └── object nào (tùy chọn; nếu bỏ trống, tất cả)
        │      └── loại object (pod, deployment, service, ingress...)
        └── get, apply, delete, describe, logs, exec, port-forward...
```

Các verb phổ biến:
- `kubectl get X` — list object loại X
- `kubectl apply -f file.yaml` — tạo hoặc cập nhật object từ YAML
- `kubectl delete -f file.yaml` — xóa object trong YAML
- `kubectl describe pod <name>` — view chi tiết (events, status, container list)
- `kubectl logs <pod>` — stdout/stderr của container đầu tiên
- `kubectl exec -it <pod> -- sh` — mở shell trong container
- `kubectl port-forward svc/X 8080:80` — tunnel local port tới Service (debug)
- `kubectl explain pod.spec` — docs built-in cho mọi trường (dùng nhiều!)

`kubectl explain` là bạn thân của bạn. Đừng học thuộc YAML field — tra cứu:
`kubectl explain deployment.spec.strategy.rollingUpdate`.

---

## 10. Namespace

Một **Namespace** là phân vùng logic của cluster. Resource trong một namespace có tên
duy nhất *trong namespace đó* — hai namespace có thể cùng có Deployment `nginx` mà
không xung đột.

- `default` — nơi stuff của bạn land nếu không specify.
- `kube-system` — pod control-plane (API server, etcd, coredns, kube-proxy).
- `local-path-storage` — local-path provisioner (CSI driver cho PVC).
- `ingress-nginx` (nếu có) — nơi ingress controller sống nếu bạn dùng một cái.
- Stage sau: `mlflow`, `kubeflow`, `argocd`, v.v.

Dùng namespace để nhóm resource liên quan (vd: một namespace per app, per team, per
environment). Bạn sẽ thấy `kubectl -n <namespace>` khắp nơi — nó scope lệnh.

---

## 11. Reconcile loop, cụ thể

Bạn sẽ thấy pattern này lặp lại cho mọi resource. Ví dụ: Deployment.

1. Bạn `kubectl apply -f deployment.yaml` → API server lưu vào etcd.
2. **Deployment controller** (trong controller-manager) nhận thấy Deployment mới.
3. Nó tạo **ReplicaSet** để quản lý N replica của Pod template.
4. **ReplicaSet controller** nhận thấy ReplicaSet mới.
5. Nó tạo N **Pod** (chỉ là object Pod trong etcd — chưa có container).
6. **Scheduler** nhận thấy Pod chưa được lên lịch, chọn node, ghi `nodeName` vào Pod.
7. **Kubelet** trên node đó nhận thấy Pod được gán cho mình.
8. kubelet gọi containerd pull image và start container.
9. kubelet báo cáo Pod status lại cho API server.
10. Nếu container chết → kubelet restart (theo Pod restartPolicy).
11. Nếu Pod chết hoàn toàn → ReplicaSet controller nhận thấy count giảm → tạo Pod
    mới → lặp lại.

Không có component đơn lẻ nào "điều hành". Mỗi controller theo dõi một phần etcd và
phản ứng. Đó là lý do k8s resilient: không có single point of failure trong logic
điều khiển.

---

## 12. Sau stage 00 bạn phải giải thích được gì

- Tại sao k8s tồn tại (orchestration, declarative, reconcile loop).
- Các thành phần control plane và mỗi cái làm gì.
- Pod / Deployment / Service / Ingress là gì ở mức cao.
- Khác biệt giữa ClusterIP, NodePort, LoadBalancer, Ingress.
- cloud-provider-kind làm gì và tại sao cần sudo.
- Tại sao `kubectl apply` hoạt động (API server → etcd → controller → kubelet →
  containerd).
- Cách kind biến Docker container thành k8s cluster.

Nếu chỗ nào mờ, đọc lại section đó trước khi sang stage 01. Stage 01 sẽ làm Pod,
Deployment, Service cụ thể bằng cách chạy chúng và quan sát reconcile loop diễn ra.

---

## Đọc thêm (docs chính thức, lấy trực tiếp)

- Kubernetes architecture: https://kubernetes.io/docs/concepts/overview/components/
- Kubernetes API fundamentals: https://kubernetes.io/docs/concepts/overview/kubernetes-api/
- Declarative vs imperative: https://kubernetes.io/docs/concepts/overview/working-with-objects/kubernetes-objects/
- kind ingress guide: https://kind.sigs.k8s.io/docs/user/ingress/
- cloud-provider-kind: https://github.com/kubernetes-sigs/cloud-provider-kind