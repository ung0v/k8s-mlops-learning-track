# 06 — Khái niệm: GitOps với Argo CD

> Bản dịch tiếng Việt của `concepts.md` — nếu có chỗ khó hiểu, tham khảo bản tiếng Anh.
> Đọc phần này trước. Sau đó chạy lab trong `README.md`.
> Đã đối chiếu với tài liệu ổn định của Argo CD (argo-cd.readthedocs.io) và manifest cài đặt thực tế.

---

## 1. GitOps là gì?

**GitOps** là một phương pháp triển khai trong đó **git là nguồn chân lý duy nhất** (single source of truth)
cho trạng thái cluster. Bạn push YAML lên một git repo; một controller trong cluster theo dõi repo đó và
**reconcile** cluster cho khớp.

```
   developer ──git push──> git repo (YAML manifests)
                              │
                              │ Argo CD watches this repo
                              ▼
                        Argo CD controller
                              │
                              │ compares git (desired) vs cluster (actual)
                              │ applies the diff
                              ▼
                        k8s cluster (Pods, Deployments, Services...)
```

### GitOps so với kubectl mệnh lệnh (imperative)
| Kiểu         | Ai thực hiện         | Nguồn chân lý          | Xử lý drift         |
|--------------|----------------------|------------------------|---------------------|
| `kubectl apply` | Bạn, thủ công     | File YAML trên Mac của bạn | Drift không nhìn thấy |
| GitOps       | Argo CD, liên tục    | git repo               | Drift được tự động sửa |

Với GitOps:
- **Audit trail**: mọi thay đổi là một git commit kèm tác giả + dấu thời gian.
- **Rollback**: `git revert` + Argo CD sync lại trạng thái cũ. Không cần `kubectl rollout undo`.
- **Multi-cluster**: Argo CD có thể triển khai cùng một repo cho các cluster dev/staging/prod.
- **Disaster recovery**: tái tạo cluster, trỏ Argo CD vào repo, mọi thứ quay lại.

---

## 2. Kiến trúc Argo CD

Argo CD chạy trong namespace `argocd` và có các thành phần sau:

- **API server** — "cửa chính". UI, CLI và các hệ thống CI nói chuyện với nó.
- **Repository server** — một sidecar clone git repo và render manifest (hỗ trợ plain YAML, Kustomize, Helm, Jsonnet).
- **Application controller** — vòng lặp reconcile. Theo dõi git để phát hiện thay đổi và cluster để phát hiện drift. Áp dụng diff.
- **Redis** — cache cho trạng thái repo và tình trạng application.
- **Dex** (tùy chọn) — identity provider cho SSO (chúng ta bỏ qua trong lab).

**Custom Resource** chính là `Application` (CRD `applications.argoproj.io`). Một Application
nói: "sync git repo/path này tới namespace của cluster này."

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: iris-serve
  namespace: argocd
spec:
  source:
    repoURL: <git repo URL>
    path: 05-serving-single-model/manifests
    targetRevision: HEAD
  destination:
    server: https://kubernetes.default.svc
    namespace: default
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

- `source.repoURL` — nơi chứa YAML. Có thể là path cục bộ nếu bạn dùng local repo (lab sẽ dùng một local git repo giả lập).
- `source.path` — thư mục trong repo chứa manifest.
- `destination.server` — `https://kubernetes.default.svc` nghĩa là "cluster này" (in-cluster).
- `syncPolicy.automated` — auto-sync khi git thay đổi. `prune: true` xóa tài nguyên đã bị gỡ khỏi git. `selfHeal: true` áp dụng lại nếu ai đó `kubectl edit` thủ công một tài nguyên (sửa drift).

---

## 3. Sync waves

Khi Argo CD sync một repo có nhiều tài nguyên, nó có thể sắp xếp thứ tự dùng **sync waves**. Sync wave
của một tài nguyên được đặt qua annotation `argocd.argoproj.io/sync-wave: "N"`. Tài nguyên có số wave
nhỏ hơn được áp dụng trước.

```yaml
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "0"   # applied first
```

Trường hợp sử dụng:
- Wave 0: Namespaces, CRDs, PVCs (infrastructure).
- Wave 1: Deployments, Services (apps).
- Wave 2: Ingress, HPA (routing + scaling — chỉ sau khi app đã lên).

Không có sync waves, Argo CD áp dụng tài nguyên theo thứ tự tùy ý, có thể thất bại (ví dụ: một
Ingress trỏ tới Service chưa tồn tại).

---

## 4. Tình trạng health và sync

Argo CD hiển thị hai trạng thái cho mỗi Application:

- **Sync status** — cluster có khớp git không?
  - `Synced` — cluster khớp git.
  - `OutOfSync` — cluster khác git (ai đó đã đổi gì đó hoặc git đã thay đổi).
  - `Unknown` — Argo CD không xác định được (thường là lỗi kết nối).
- **Health status** — các tài nguyên có healthy không?
  - `Healthy` — mọi Pod Ready, mọi Deployment available, v.v.
  - `Progressing` — vẫn đang rollout.
  - `Degraded` — một số Pod đang crash.
  - `Missing` — một tài nguyên có trong git nhưng không có trong cluster.

Hai trạng thái này **độc lập**: một app có thể `Synced` nhưng `Degraded` (manifest đã apply nhưng Pod
đang crash). Hoặc `OutOfSync` nhưng `Healthy` (git có phiên bản mới chưa apply, phiên bản cũ
vẫn chạy ngon).

---

## 5. Lab hoạt động thế nào

Vì chúng ta không có public git repo, lab dùng một **local git repo** trên Mac làm nguồn. Argo CD
có thể đọc từ path cục bộ nếu bạn cấu hình `repoURL` trỏ tới path file cục bộ (Argo CD hỗ trợ URL
`file://` trong dev mode, hoặc bạn có thể dùng local bare repo).

Để đơn giản, lab sẽ:
1. Cài Argo CD.
2. Tạo một `Application` trỏ tới manifest của stage 05 (dùng `repoURL` là path của local git repo).
3. Theo dõi Argo CD sync serving app.
4. Thay đổi manifest (đổi replicas), commit, và xem Argo CD auto-sync.
5. `kubectl scale` thủ công và xem Argo CD self-heal lại.

> **Lưu ý:** Cho một GitOps setup thật, bạn nên push repo lên GitHub/GitLab và trỏ Argo CD
> tới URL đó. Cách dùng local-repo chỉ để học cơ chế mà không cần remote git host.

---

## 6. Những gì bạn cần giải thích được sau stage 06

- GitOps là gì và khác `kubectl apply` thế nào.
- Các thành phần của Argo CD và Application CRD làm gì.
- `syncPolicy.automated.selfHeal: true` nghĩa là gì (sửa drift).
- Sync waves là gì và khi nào dùng.
- Khác biệt giữa sync status và health status.
- Tại sao `git revert` là rollback của GitOps (không cần `kubectl rollout undo`).

---

## 7. Đọc thêm

- Argo CD getting started: https://argo-cd.readthedocs.io/en/stable/getting_started/
- Argo CD core concepts: https://argo-cd.readthedocs.io/en/stable/core_concepts/
- Argo CD sync waves: https://argo-cd.readthedocs.io/en/stable/user-guide/sync-waves/
- Argo CD auto-sync + self-heal: https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/
- GitOps principles (OpenGitOps): https://opengitops.dev/