# 02 — Lab: Storage, Config, and StatefulSets

> Read `concepts.md` first. Then run this lab.
> Goal: see PVC persistence, ConfigMap/Secret injection, a StatefulSet with stable identity, and an init container.

---

## Objectives

1. Inject config + secrets into a Pod (env vars + mounted files).
2. Create a PVC and a Pod that uses it — write data, delete the Pod, see the data persist.
3. Run a StatefulSet with 3 replicas — see ordered creation, stable names, per-Pod PVCs.
4. See the headless Service give each Pod a DNS name.
5. Use an init container to prepare a file the main container serves.
6. Clean up.

---

## 0. Prerequisites

- kind cluster running.
- `local-path` StorageClass available (kind ships with it). Verify:

```bash
kubectl get sc
```

You should see `local-path (default)`.

---

## 1. ConfigMap + Secret injection

Apply the ConfigMap and Secret:

```bash
kubectl apply -f manifests/configmap.yaml
kubectl apply -f manifests/secret.yaml
```

Verify:

```bash
kubectl get cm app-config
kubectl get secret db-secret
```

Inspect the ConfigMap content:

```bash
kubectl describe cm app-config
```

Note the `Data` section shows the keys and values.

Inspect the Secret:

```bash
kubectl describe secret db-secret
```

Note: `describe` does NOT show the secret values (only key names + sizes). To see the
base64-encoded values:

```bash
kubectl get secret db-secret -o yaml
```

Decode a value (confirm it's not encrypted, just base64):

```bash
kubectl get secret db-secret -o jsonpath='{.data.password}' | base64 --decode
echo
```

Expected: `s3cr3t!`

Apply the Pod that consumes them:

```bash
kubectl apply -f manifests/config-secret-pod.yaml
kubectl wait --for=condition=Ready pod/config-demo --timeout=60s
```

Verify env vars:

```bash
kubectl exec config-demo -- sh -c 'echo "LOG_LEVEL=$LOG_LEVEL"; echo "GREETING=$GREETING"; echo "DB_USER=$DB_USER"; echo "DB_PASS=$DB_PASS"'
```

Expected:

```
LOG_LEVEL=info
GREETING=hello from configmap
DB_USER=admin
DB_PASS=s3cr3t!
```

Verify mounted files (ConfigMap as a volume — each key becomes a file):

```bash
kubectl exec config-demo -- ls /etc/config
kubectl exec config-demo -- cat /etc/config/app.properties
kubectl exec config-demo -- cat /etc/config/greeting
```

Verify Secret mounted as a volume:

```bash
kubectl exec config-demo -- ls /etc/secret
kubectl exec config-demo -- cat /etc/secret/username
echo
kubectl exec config-demo -- cat /etc/secret/password
echo
```

Expected: `admin` and `s3cr3t!`.

Clean up the demo Pod (keep the ConfigMap and Secret for later stages):

```bash
kubectl delete -f manifests/config-secret-pod.yaml
```

---

## 2. Persistent storage with a PVC

Create the PVC:

```bash
kubectl apply -f manifests/pvc.yaml
kubectl get pvc data-pvc
```

Expected (might be `Pending` for a few seconds, then `Bound`):

```
NAME       STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   AGE
data-pvc   Bound    pvc-<uuid>                                 100Mi      RWO             local-path     3s
```

If it's stuck in `Pending`, wait a few seconds and re-run. kind's local-path provisioner
creates the PV on demand.

Create a Pod that uses the PVC and writes data to it:

```bash
kubectl apply -f manifests/pvc-pod.yaml
kubectl wait --for=condition=Ready pod/pvc-demo --timeout=60s
```

Write a file into the mounted volume:

```bash
kubectl exec pvc-demo -- sh -c 'echo "important data written at $(date)" > /data/note.txt'
kubectl exec pvc-demo -- cat /data/note.txt
```

Verify the PV was created and is bound:

```bash
kubectl get pv
```

You should see a `pvc-<uuid>` PV with `CLAIM=data-pvc/data` and `STATUS=Bound`.

Now delete the Pod — the PVC and its data survive:

```bash
kubectl delete -f manifests/pvc-pod.yaml
kubectl get pvc data-pvc
```

The PVC is still there (Bound). Let's mount it in a new Pod and confirm the data is still present:

```bash
kubectl apply -f manifests/pvc-pod.yaml
kubectl wait --for=condition=Ready pod/pvc-demo --timeout=60s
kubectl exec pvc-demo -- cat /data/note.txt
```

Expected: the same `important data written at <date>` line. The data survived the Pod deletion
because it lived on the PVC, not on the Pod's ephemeral filesystem.

Clean up:

```bash
kubectl delete -f manifests/pvc-pod.yaml
kubectl delete -f manifests/pvc.yaml
```

When the PVC is deleted, local-path's default reclaim policy (`Delete`) deletes the PV and its
data. Verify:

```bash
kubectl get pv
```

Should be empty (or the PV is in `Released`/terminating state).

---

## 3. StatefulSet with stable identity

Apply the headless Service and StatefulSet:

```bash
kubectl apply -f manifests/headless-service.yaml
kubectl apply -f manifests/statefulset.yaml
```

Watch the Pods come up **one at a time** (ordered, not parallel):

```bash
kubectl get pods -l app=web -w
```

Expected (sequential creation):

```
NAME    READY   STATUS              RESTARTS   AGE
web-0   0/1     Pending             0          0s
web-0   0/1     Pending             0          1s
web-0   0/1     ContainerCreating   0          2s
web-0   1/1     Running             0          4s
web-1   0/1     Pending             0          0s
web-1   0/1     ContainerCreating   0          2s
web-1   1/1     Running             0          4s
web-2   0/1     Pending             0          0s
web-2   0/1     ContainerCreating   0          2s
web-2   1/1     Running             0          4s
```

Press `Ctrl+C` when all three are Running.

Note the **stable, predictable names**: `web-0`, `web-1`, `web-2`. Compare to a Deployment's
random-hash names from stage 01.

### See the per-Pod PVCs

```bash
kubectl get pvc -l app=web
```

Expected (one PVC per replica, named `<volumeClaimTemplate.name>-<pod-name>`):

```
NAME        STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   AGE
www-web-0   Bound    pvc-<uuid>                                 50Mi       RWO            local-path     30s
www-web-1   Bound    pvc-<uuid>                                 50Mi       RWO            local-path     25s
www-web-2   Bound    pvc-<uuid>                                 50Mi       RWO            local-path     20s
```

Each Pod has its **own** PVC. This is the key difference from a Deployment, where all
replicas would share one PVC (or none).

### Write unique data to each Pod

```bash
kubectl exec web-0 -- sh -c 'echo "I am web-0" > /usr/share/nginx/html/index.html'
kubectl exec web-1 -- sh -c 'echo "I am web-1" > /usr/share/nginx/html/index.html'
kubectl exec web-2 -- sh -c 'echo "I am web-2" > /usr/share/nginx/html/index.html'
```

### Verify via the headless Service DNS

From a debug pod, resolve each Pod's DNS name (only works with the headless Service):

```bash
kubectl run debug --rm -i --image=curlimages/curl:8.12.0 --restart=Never -- sh -c 'for i in 0 1 2; do echo "=== web-$i ==="; curl -s http://web-$i.web-svc/; done'
```

Expected (each Pod serves its unique content):

```
=== web-0 ===
I am web-0
=== web-1 ===
I am web-1
=== web-2 ===
I am web-2
```

This is the magic of a headless Service + StatefulSet: each Pod has a stable DNS name.

### Self-healing with stable identity

Delete one Pod and watch it come back with the **same name**:

```bash
kubectl delete pod web-1
kubectl get pods -l app=web -w
```

Expected: `web-1` is recreated (not `web-3` or a random name). Once it's Running again:

```bash
kubectl exec web-1 -- cat /usr/share/nginx/html/index.html
```

Expected: `I am web-1` — the data survived because the StatefulSet reattached the same
PVC (`www-web-1`) to the new `web-1` Pod.

### Scale down (ordered deletion)

```bash
kubectl scale statefulset/web --replicas=1
kubectl get pods -l app=web -w
```

Expected: Pods are deleted in **reverse order** (`web-2`, then `web-1`). `web-0` stays.
The PVCs for the deleted Pods are **not** deleted (they're retained in case you scale back up).

```bash
kubectl get pvc -l app=web
```

You'll still see all three PVCs (`www-web-0`, `www-web-1`, `www-web-2`).

### Clean up the StatefulSet

```bash
kubectl delete -f manifests/statefulset.yaml
kubectl delete -f manifests/headless-service.yaml
kubectl delete pvc -l app=web
```

---

## 4. Init container

Apply the init-container Pod and a Service to reach it:

```bash
kubectl apply -f manifests/init-pod.yaml
```

Watch the init container run first, then the main container start:

```bash
kubectl get pod init-demo -w
```

Expected:

```
NAME        READY   STATUS     RESTARTS   AGE
init-demo   0/1     Init:0/1   0          2s
init-demo   0/1     PodInitializing   0    3s
init-demo   1/1     Running          0    5s
```

The `Init:0/1` means "0 of 1 init containers have completed". Once it finishes, the main
container starts.

See the init container's logs:

```bash
kubectl logs init-demo -c init
```

Expected:

```
init done
```

### Reach the nginx container

Two options (try (a) first; (b) is a fallback):

**Option (a): port-forward (simplest, always works)**

```bash
kubectl port-forward pod/init-demo 8080:80
```

In another terminal:

```bash
curl http://localhost:8080/
```

Expected:

```
<h1>Hello from init container</h1>
```

**Option (b): LoadBalancer Service (needs cloud-provider-kind running)**

```bash
kubectl apply -f manifests/init-service.yaml
kubectl get svc init-svc
```

If `EXTERNAL-IP` is assigned, curl it:

```bash
curl http://$(kubectl get svc init-svc -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
```

> **Note:** On single-node kind, the LB container route to a single Pod can be flaky
> (the LB connects but HTTP times out). This is a kind networking quirk, not a manifest
> issue — the same Pod is reachable via port-forward and from inside the cluster. The
> LB works reliably when there are multiple replicas behind the Service (as with the
> StatefulSet demo in §3). For single-Pod demos, prefer port-forward.

### Clean up

```bash
kubectl delete -f manifests/init-service.yaml
kubectl delete -f manifests/init-pod.yaml
```

---

## 5. Clean up everything

```bash
kubectl delete -f manifests/configmap.yaml
kubectl delete -f manifests/secret.yaml
```

Verify the cluster is clean:

```bash
kubectl get pods
kubectl get pvc
kubectl get pv
```

All should be empty (or show only system resources in other namespaces).

---

## 6. What "done" looks like

You can:
- Explain why a PVC survives Pod deletion but an `emptyDir` does not.
- Inject a ConfigMap as env vars AND as mounted files, and know when each is appropriate.
- Decode a Secret value and explain why base64 is not encryption.
- Explain why a StatefulSet gives Pods stable names and per-Pod PVCs (vs a Deployment).
- Use a headless Service to address individual StatefulSet Pods by DNS name.
- Explain the `Init:0/1` status and what an init container is for.
- Draw the StatefulSet → Pod → PVC → PV → disk relationship.

---

## Try next

`../03-packaging-ml-apps/` — multi-stage Docker builds, slim ML images, `kind load docker-image`,
running your own Python app on the cluster.

---

## Troubleshooting

- **PVC stuck in `Pending`** — check `kubectl describe pvc <name>` events. The most common
  cause is specifying a `storageClassName` that doesn't exist. In kind, the default
  StorageClass is `standard` (provisioner `rancher.io/local-path`). If you omit
  `storageClassName`, k8s uses the default — which is the safest approach. Check with
  `kubectl get sc`. Also, `standard` uses `WaitForFirstConsumer` binding — the PVC stays
  Pending until a Pod actually requests it (that's normal, not a bug).
- **StatefulSet stuck at `web-0`** — the first Pod must be Ready before the second is created.
  `kubectl describe pod web-0` to see why it's not ready.
- **`curl web-0.web-svc` doesn't resolve** — only works from inside the cluster (use a debug
  pod), and only with a headless Service (clusterIP: None).
- **Init container status `Init:CrashLoopBackOff`** — `kubectl logs <pod> -c <init-container-name>`
  to see why it failed. The main container won't start until all init containers succeed.
- **LoadBalancer `EXTERNAL-IP` pending** — cloud-provider-kind isn't running. Start it in a
  separate terminal (`sudo "$(go env GOPATH)/bin/cloud-provider-kind" --enable-default-ingress=true`)
  or use `kubectl port-forward` instead.