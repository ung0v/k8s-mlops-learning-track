# 01 — Lab: Pods, Deployments, Services

> Read `concepts.md` first. Then run this lab against your kind cluster.
> Goal: see the reconcile loop in action, see labels connect things, see a Service route traffic.

---

## Objectives

1. Create a Pod from a manifest and inspect it.
2. Create a Deployment, watch it spawn 3 Pods, scale it, roll out a new image.
3. Create a ClusterIP Service and reach it from inside the cluster.
4. Prove that Labels + Selectors are the connective tissue.
5. See the hierarchy: Deployment → ReplicaSet → Pod.
6. Clean up everything you created.

---

## 0. Prerequisites

- kind cluster running (`kubectl get nodes` → `kind-control-plane` Ready).
- `cloud-provider-kind` running in its terminal (only needed for Ingress/LB, not for this stage's ClusterIP work).
- Working directory: `01-k8s-fundamentals/` of this repo.

---

## 1. Create a single Pod

Apply the Pod manifest:

```bash
kubectl apply -f manifests/pod.yaml
```

Expected output:

```
pod/nginx-pod created
```

Watch it become Ready (should take a few seconds):

```bash
kubectl get pods -w
```

You should see:

```
NAME        READY   STATUS    RESTARTS   AGE
nginx-pod   1/1     Running   0          5s
```

Press `Ctrl+C` to stop the watch.

Inspect the Pod in detail:

```bash
kubectl describe pod nginx-pod
```

Key things to look for in the output:
- **`IP:` field** — e.g. `10.244.0.5`. This is the Pod's ephemeral IP. Note it; we'll curl it.
- **`Node:` field** — `kind-control-plane/...` — which node it was scheduled on (the only one we have).
- **`Labels:`** — `app=nginx,tier=frontend` — what the Service will later match.
- **`Events:` section at the bottom** — shows scheduler → kubelet → pulling image → created container → started container.

Get just the Pod's IP with jsonpath:

```bash
POD_IP=$(kubectl get pod nginx-pod -o jsonpath='{.status.podIP}')
echo $POD_IP
```

Curl the Pod directly from inside the cluster using a temporary debug pod:

```bash
kubectl run debug --rm -it --image=curlimages/curl:8.12.0 --restart=Never -- curl -s http://$POD_IP/
```

You should see the nginx welcome page HTML (`<title>Welcome to nginx!</title>`).
The `--rm` removes the debug pod when the curl command exits; `-it` gives you interactive output.

> Why curl from a debug pod and not from your Mac? Pod IPs live on the kind Docker
> network (`10.244.0.0/16`) which isn't reachable from the host. The Service (step 3)
> makes it reachable in-cluster via DNS, and Ingress (stage 00 skill) makes it reachable
> from the host.

### Delete the standalone Pod

```bash
kubectl delete -f manifests/pod.yaml
```

Expected:

```
pod "nginx-pod" deleted
```

This Pod won't come back because nothing owns it. (If it were managed by a ReplicaSet, the
controller would recreate it immediately — you'll see that in the next section.)

---

## 2. Create a Deployment

Apply the Deployment manifest:

```bash
kubectl apply -f manifests/deployment.yaml
```

Expected:

```
deployment.apps/nginx-deploy created
```

Watch the Pods come up — this time there should be 3 (replicas: 3):

```bash
kubectl get pods -l app=nginx -w
```

Expected (the pod names are `<deploy>-<random>-<random>`):

```
NAME                            READY   STATUS              RESTARTS   AGE
nginx-deploy-78c4b8b4-abc12     0/1     ContainerCreating   0          1s
nginx-deploy-78c4b8b4-def34     0/1     ContainerCreating   0          1s
nginx-deploy-78c4b8b4-ghi56     0/1     ContainerCreating   0          1s
nginx-deploy-78c4b8b4-abc12     1/1     Running             0          3s
nginx-deploy-78c4b8b4-def34     1/1     Running             0          3s
nginx-deploy-78c4b8b4-ghi56     1/1     Running             0          3s
```

The hash suffixes are stable for a given ReplicaSet revision. Press `Ctrl+C` once all are Running.

### See the hierarchy

```bash
kubectl get deployment nginx-deploy
kubectl get rs -l app=nginx
kubectl get pods -l app=nginx
```

You'll see:
- 1 Deployment named `nginx-deploy`
- 1 ReplicaSet named `nginx-deploy-<hash>` with `DESIRED=3, CURRENT=3, READY=3`
- 3 Pods named `nginx-deploy-<hash>-<rand>`

That's the Deployment → ReplicaSet → Pod hierarchy in front of you.

### Scale the Deployment imperatively

```bash
kubectl scale deployment/nginx-deploy --replicas=5
kubectl get pods -l app=nginx -w
```

You should see 2 new Pods appear. Press `Ctrl+C`.

Verify the ReplicaSet noticed:

```bash
kubectl get rs -l app=nginx
```

`DESIRED` should be `5` now. The Deployment's spec.replicas is unchanged in etcd (the
manifest didn't change) — only the live state. Run `kubectl get deployment nginx-deploy -o yaml | grep replicas:` to confirm.

### Self-healing demo — kill a Pod

Pick one Pod name from `kubectl get pods -l app=nginx`, then delete it:

```bash
kubectl delete pod <paste-one-pod-name>
kubectl get pods -l app=nginx
```

Expected: 5 Pods again within seconds. The ReplicaSet noticed the count dropped to 4 and
created a new Pod to get back to 5. The deleted Pod is gone forever — its replacement has
a new name and a **new IP**.

### Roll out a new image version

Bump the image from `nginx:1.27` to `nginx:1.28`:

```bash
kubectl set image deployment/nginx-deploy nginx=nginx:1.28
kubectl rollout status deployment/nginx-deploy
```

Expected:

```
deployment "nginx-deploy" successfully rolled out
```

Watch the rollout happen (run this while the rollout is in progress):

```bash
kubectl get rs -l app=nginx -w
```

You'll see:
- A **new** ReplicaSet (revision 2) scale up to 5.
- The **old** ReplicaSet (revision 1) scale down to 0 (kept for rollback).

### Rollback

```bash
kubectl rollout history deployment/nginx-deploy
kubectl rollout undo deployment/nginx-deploy
kubectl rollout status deployment/nginx-deploy
```

You should now be back on revision 1 (nginx:1.27). Verify:

```bash
kubectl get deployment nginx-deploy -o jsonpath='{.spec.template.spec.containers[0].image}'
echo
```

Expected: `nginx:1.27`.

### Resize back to 3 for the next section

```bash
kubectl scale deployment/nginx-deploy --replicas=3
```

---

## 3. Create a Service

Apply the Service manifest:

```bash
kubectl apply -f manifests/service.yaml
```

Expected:

```
service/nginx-svc created
```

Inspect it:

```bash
kubectl get svc nginx-svc
```

Expected:

```
NAME        TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)   AGE
nginx-svc   ClusterIP   10.96.x.y       <none>        80/TCP    5s
```

The `CLUSTER-IP` is a virtual IP from the cluster's service CIDR (`10.96.0.0/12` by
default). It's stable for the lifetime of the Service.

See the Endpoints (the Pod IPs the Service routes to):

```bash
kubectl get endpoints nginx-svc
```

Expected (3 IPs, since the Deployment has 3 replicas):

```
NAME        ENDPOINTS                                       AGE
nginx-svc   10.244.0.5:80,10.244.0.6:80,10.244.0.7:80      30s
```

These match the Pod IPs from `kubectl get pods -l app=nginx -o wide`.

> **Note:** k8s v1.33+ prints a deprecation warning for `v1 Endpoints` and recommends
> `discovery.k8s.io/v1 EndpointSlice`. EndpointSlices are the modern backing store for
> Service endpoints (each Service has 1+ slices, each holding up to 100 endpoints). The
> `kubectl get endpoints` command still works and is fine for learning; for production
> use `kubectl get endpointslices`.

### Reach the Service from inside the cluster

```bash
kubectl run debug --rm -it --image=curlimages/curl:8.12.0 --restart=Never -- curl -s http://nginx-svc/
```

You should see the nginx welcome page. Note we used the **Service name** `nginx-svc`, not
any IP — DNS resolved it inside the cluster.

### Prove load balancing

Hit the Service a few times from a debug pod with a longer-lived shell:

```bash
kubectl run debug --rm -it --image=curlimages/curl:8.12.0 --restart=Never -- sh -c 'for i in 1 2 3 4 5 6; do curl -s http://nginx-svc/ | grep "Welcome"; done'
```

You'll get 6 responses. To prove round-robin, check the endpoints each hit went to — for
that, ask nginx for its server hostname via a custom header it echoes. We'll skip the deep
proof here and just trust that kube-proxy is round-robining (it is, via iptables RANDOM
mode or IPVS rr).

---

## 4. Prove Labels connect things

### Filter Pods by label

```bash
kubectl get pods -l app=nginx
kubectl get pods -l tier=frontend
kubectl get pods -l env=prod
```

The third command returns nothing — we never set `env=prod`. Selectors only match what's there.

### See the selector the Deployment uses

```bash
kubectl get deployment nginx-deploy -o jsonpath='{.spec.selector.matchLabels}'
echo
```

Expected: `{"app":"nginx"}`. That's the **same** label the Service selector uses.

### See the selector the Service uses

```bash
kubectl get svc nginx-svc -o jsonpath='{.spec.selector}'
echo
```

Expected: `{"app":"nginx"}`. Same label. That's why the Service routes to those Pods.

### Break the connection (and fix it)

Label-mismatch is the #1 beginner bug. Simulate it:

```bash
kubectl edit svc nginx-svc
```

In your editor, change `app: nginx` under `spec.selector` to `app: notnginx`. Save & exit.

Now check the endpoints:

```bash
kubectl get endpoints nginx-svc
```

Expected:

```
NAME        ENDPOINTS   AGE
nginx-svc   <none>      2m
```

No endpoints — the Service is now pointing at nothing because no Pods match `app=notnginx`.
Try curling from a debug pod:

```bash
kubectl run debug --rm -it --image=curlimages/curl:8.12.0 --restart=Never -- curl -s --max-time 3 http://nginx-svc/
```

It will hang and time out. Fix it:

```bash
kubectl edit svc nginx-svc
```

Change `app: notnginx` back to `app: nginx`. Save & exit. Verify:

```bash
kubectl get endpoints nginx-svc
```

Three IPs are back. This proves the link between Service and Pods is **only** the label.

---

## 5. Use `kubectl explain` (your best friend)

You don't need to memorize YAML. Look up fields:

```bash
kubectl explain pod.spec.containers.resources
kubectl explain deployment.spec.strategy.rollingUpdate.maxSurge
kubectl explain service.spec.ports
```

The output gives you the field type, whether it's required, and a short description. Use
this every time you forget a field name.

---

## 6. Clean up

```bash
kubectl delete -f manifests/service.yaml
kubectl delete -f manifests/deployment.yaml
```

Verify:

```bash
kubectl get all -l app=nginx
```

Should be empty. The `app=nginx` label was on Deployment, ReplicaSet, Pod, and Service —
`kubectl get all -l app=nginx` filtered them all out, confirming everything's gone.

---

## 7. What "done" looks like

You can:
- Read a Pod / Deployment / Service YAML and explain each field.
- Watch `kubectl get pods -w` and recognize the Pending → ContainerCreating → Running progression.
- Explain why deleting a Deployment's Pod doesn't kill the app (the ReplicaSet recreates it).
- Explain why the Service kept working when you rolled the image (selector unchanged).
- Draw the Deployment → ReplicaSet → Pod hierarchy with the Service attached by label.

---

## Try next

`../02-storage-config/` — PersistentVolumes, PersistentVolumeClaims, StatefulSets,
ConfigMaps, Secrets, init containers. Where Pods get their data and config.

---

## Troubleshooting

- **`ImagePullBackOff`** — image name typo or no network. Check `kubectl describe pod <name>`.
- **Pod stuck in `Pending`** — scheduler can't place it. `kubectl describe pod <name>` → Events. Usually resource requests too high for the single kind node.
- **Service `ENDPOINTS <none>`** — selector doesn't match any Pod labels. Re-read §4 above.
- **`curl` from debug pod hangs** — same cause: no endpoints. Also could be a NetworkPolicy (we have none in kind by default).
- **`kubectl rollout status` hangs** — a rollout that can never finish (e.g. the new image crashes). `kubectl rollout undo deployment/<name>` to recover.