# 06 — Concepts: GitOps with Argo CD

> Read this first. Then run the lab in `README.md`.
> Verified against Argo CD stable docs (argo-cd.readthedocs.io) and the live install manifest.

---

## 1. What is GitOps?

**GitOps** is a deployment methodology where **git is the single source of truth** for your
cluster state. You push YAML to a git repo; a controller in the cluster watches the repo and
**reconciles** the cluster to match.

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

### GitOps vs imperative kubectl
| Style         | Who acts              | Source of truth        | Drift handling       |
|---------------|----------------------|------------------------|---------------------|
| `kubectl apply` | You, manually       | YAML files on your Mac | Drift is invisible  |
| GitOps        | Argo CD, continuously| git repo              | Drift is auto-corrected |

With GitOps:
- **Audit trail**: every change is a git commit with author + timestamp.
- **Rollback**: `git revert` + Argo CD syncs the old state. No `kubectl rollout undo` needed.
- **Multi-cluster**: Argo CD can deploy the same repo to dev/staging/prod clusters.
- **Disaster recovery**: recreate the cluster, point Argo CD at the repo, everything comes back.

---

## 2. Argo CD architecture

Argo CD runs in the `argocd` namespace and has these components:

- **API server** — the front door. The UI, CLI, and CI systems talk to it.
- **Repository server** — a sidecar that clones git repos and renders manifests (supports plain YAML, Kustomize, Helm, Jsonnet).
- **Application controller** — the reconcile loop. Watches git for changes and the cluster for drift. Applies the diff.
- **Redis** — cache for repo state and application status.
- **Dex** (optional) — identity provider for SSO (we skip this in the lab).

The key **Custom Resource** is `Application` (CRD `applications.argoproj.io`). An Application
says: "sync this git repo/path to this cluster namespace."

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

- `source.repoURL` — where the YAML lives. Can be a local path if you're using a local repo (we'll use a fake local git repo for the lab).
- `source.path` — the directory in the repo containing the manifests.
- `destination.server` — `https://kubernetes.default.svc` means "this cluster" (in-cluster).
- `syncPolicy.automated` — auto-sync on git changes. `prune: true` deletes resources removed from git. `selfHeal: true` re-applies if someone manually `kubectl edit`s a resource (drift correction).

---

## 3. Sync waves

When Argo CD syncs a repo with many resources, it can order them using **sync waves**. A
resource's sync wave is set via the annotation `argocd.argoproj.io/sync-wave: "N"`. Resources
with lower wave numbers are applied first.

```yaml
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "0"   # applied first
```

Use cases:
- Wave 0: Namespaces, CRDs, PVCs (infrastructure).
- Wave 1: Deployments, Services (apps).
- Wave 2: Ingress, HPA (routing + scaling — only after the app is up).

Without sync waves, Argo CD applies resources in arbitrary order, which can fail (e.g. an
Ingress pointing at a Service that doesn't exist yet).

---

## 4. Health and sync status

Argo CD shows two statuses for each Application:

- **Sync status** — does the cluster match git?
  - `Synced` — cluster matches git.
  - `OutOfSync` — cluster differs from git (someone changed something or git moved).
  - `Unknown` — Argo CD can't determine (usually a connection error).
- **Health status** — are the resources healthy?
  - `Healthy` — all Pods Ready, all Deployments available, etc.
  - `Progressing` — still rolling out.
  - `Degraded` — some Pods are crashing.
  - `Missing` — a resource in git isn't in the cluster.

These are **independent**: an app can be `Synced` but `Degraded` (manifests applied but Pods
crashing). Or `OutOfSync` but `Healthy` (git has a new version not yet applied, old version
still running fine).

---

## 5. How the lab works

Since we don't have a public git repo, the lab uses a **local git repo** on your Mac as the
source. Argo CD can read from a local path if you configure it with `repoURL` pointing to a
local file path (Argo CD supports `file://` URLs in dev mode, or you can use a local bare
repo).

For simplicity, the lab will:
1. Install Argo CD.
2. Create an `Application` pointing at the stage 05 manifests (using `repoURL` as a local
   git repo path).
3. Watch Argo CD sync the serving app.
4. Make a change to the manifest (change replicas), commit, and watch Argo CD auto-sync.
5. Manually `kubectl scale` and watch Argo CD self-heal it back.

> **Note:** For a real GitOps setup, you'd push the repo to GitHub/GitLab and point Argo CD
> at that URL. The local-repo approach is for learning the mechanism without a remote git host.

---

## 6. What you should be able to explain after stage 06

- What GitOps is and how it differs from `kubectl apply`.
- The Argo CD components and what the Application CRD does.
- What `syncPolicy.automated.selfHeal: true` means (drift correction).
- What sync waves are and when to use them.
- The difference between sync status and health status.
- Why `git revert` is the GitOps rollback (no `kubectl rollout undo`).

---

## 7. Further reading

- Argo CD getting started: https://argo-cd.readthedocs.io/en/stable/getting_started/
- Argo CD core concepts: https://argo-cd.readthedocs.io/en/stable/core_concepts/
- Argo CD sync waves: https://argo-cd.readthedocs.io/en/stable/user-guide/sync-waves/
- Argo CD auto-sync + self-heal: https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/
- GitOps principles (OpenGitOps): https://opengitops.dev/