# Ba cluster Kind (management + dev + prod) – giống cloud

Argo CD cài **chỉ** trên **cluster management**. Deploy app dev sang cluster **dev**, app prod sang cluster **prod**. Cần expose API server của dev và prod ra host để Argo CD (chạy trong management) gọi được.

---

## 1. Tạo 3 cluster Kind

```bash
# Từ thư mục gốc repo
kind create cluster --name management --config kind/management-kind-config.yaml
kind create cluster --name dev --config kind/dev-kind-config.yaml
kind create cluster --name prod --config kind/prod-kind-config.yaml
```

- **management**: API server trên host tại `127.0.0.1:33443` (Argo CD chạy ở đây)
- **dev**: API server trên host tại `127.0.0.1:30443`
- **prod**: API server trên host tại `127.0.0.1:31443`

Kiểm tra:

```bash
kubectl config get-contexts
# kind-management  kind-management  ...
# kind-dev         kind-dev         ...
# kind-prod        kind-prod        ...
```

**Nếu `kubectl` báo lỗi TLS** (`x509: certificate is valid for ..., not 0.0.0.0`): kubeconfig đang trỏ server `0.0.0.0` — certificate API server không có SAN đó. Sửa bằng cách trỏ cluster sang `127.0.0.1` (chi tiết: **README.md**, mục lỗi TLS):

```bash
kubectl config set-cluster kind-management --server=https://127.0.0.1:33443
kubectl config set-cluster kind-dev --server=https://127.0.0.1:30443
kubectl config set-cluster kind-prod --server=https://127.0.0.1:31443
```

---

## 2. Cài Argo CD trên cluster management

```bash
kubectl config use-context kind-management

kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

kubectl -n argocd wait --for=condition=Ready pods --all --timeout=300s
```

Lấy password admin (user `admin`):

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d && echo
```

Port-forward UI/API (giữ terminal mở hoặc chạy nền):

```bash
kubectl -n argocd port-forward svc/argocd-server 8080:443
# Login: https://localhost:8080, user admin
```

---

## 3. Đăng ký cluster “dev” và “prod” với Argo CD (trên management)

Argo CD chạy **trong** cluster management. Để nó deploy sang dev và prod, nó phải gọi API server của dev và prod. Từ pod trong management, địa chỉ “máy host” là:

- **Mac/Windows (Docker Desktop):** `host.docker.internal`
- **Linux (Kind):** dùng **`172.18.0.1`** — Kind tạo network `kind` với gateway 172.18.0.1; từ pod trong management phải dùng IP này để ra host (port 30443/31443). Nếu dùng `172.17.0.1` sẽ bị **dial tcp ... i/o timeout**.

Dev API = `https://<host>:30443`, Prod API = `https://<host>:31443`.

### 3.1. Tạo ServiceAccount và token trên cluster dev

```bash
kubectl --context kind-dev apply -f kind/dev-argocd-manager.yaml
sleep 5
```

Lấy token dev (giữ nguyên terminal để dùng biến `$DEV_TOKEN` ở bước 3.3):

```bash
DEV_TOKEN=$(kubectl --context kind-dev get secret argocd-manager-long-lived-token -n kube-system -o jsonpath='{.data.token}' | base64 -d)
echo "$DEV_TOKEN"
```

### 3.2. Tạo ServiceAccount và token trên cluster prod

```bash
kubectl --context kind-prod apply -f kind/prod-argocd-manager.yaml
sleep 5
```

Lấy token prod (giữ nguyên terminal để dùng biến `$PROD_TOKEN` ở bước 3.3):

```bash
PROD_TOKEN=$(kubectl --context kind-prod get secret argocd-manager-long-lived-token -n kube-system -o jsonpath='{.data.token}' | base64 -d)
echo "$PROD_TOKEN"
```

### 3.3. Tạo Secret cluster “dev” và “prod” trong Argo CD (trên management)

Chạy **cùng shell** sau khi đã chạy 3.1 và 3.2 (để có biến `$DEV_TOKEN`, `$PROD_TOKEN`).

**Trên Mac/Windows:**

```bash
kubectl config use-context kind-management

kubectl create secret generic cluster-dev \
  -n argocd \
  --from-literal=name=dev \
  --from-literal=server=https://host.docker.internal:30443 \
  --from-literal=config="{\"bearerToken\":\"$DEV_TOKEN\",\"tlsClientConfig\":{\"insecure\":true}}"
kubectl label secret cluster-dev -n argocd argocd.argoproj.io/secret-type=cluster

kubectl create secret generic cluster-prod \
  -n argocd \
  --from-literal=name=prod \
  --from-literal=server=https://host.docker.internal:31443 \
  --from-literal=config="{\"bearerToken\":\"$PROD_TOKEN\",\"tlsClientConfig\":{\"insecure\":true}}"
kubectl label secret cluster-prod -n argocd argocd.argoproj.io/secret-type=cluster
```

**Trên Linux** (Kind dùng network gateway **172.18.0.1**; nếu timeout thử `ip addr show docker0` hoặc `docker network inspect kind` xem Gateway):

```bash
kubectl config use-context kind-management

kubectl create secret generic cluster-dev \
  -n argocd \
  --from-literal=name=dev \
  --from-literal=server=https://172.18.0.1:30443 \
  --from-literal=config="{\"bearerToken\":\"$DEV_TOKEN\",\"tlsClientConfig\":{\"insecure\":true}}"
kubectl label secret cluster-dev -n argocd argocd.argoproj.io/secret-type=cluster

kubectl create secret generic cluster-prod \
  -n argocd \
  --from-literal=name=prod \
  --from-literal=server=https://172.18.0.1:31443 \
  --from-literal=config="{\"bearerToken\":\"$PROD_TOKEN\",\"tlsClientConfig\":{\"insecure\":true}}"
kubectl label secret cluster-prod -n argocd argocd.argoproj.io/secret-type=cluster
```

---

## 4. Add repo Git và apply bootstrap (trên management)

```bash
kubectl config use-context kind-management
cd /path/to/practice_RKE2   # hoặc learning_RKE2

argocd login localhost:8080 --insecure --username admin --password "<admin_password>"
argocd repo add https://github.com/minhtri1612/learning_RKE2.git

kubectl apply -f argocd/projects/
kubectl apply -f argocd/repositories/
kubectl apply -f argocd/bootstrap/02-root-app.yaml
```

Sau khi root app sync xong, app có `destination.name: dev` sẽ deploy sang cluster **dev**, app có `destination.name: prod` sang cluster **prod**.

---

## 5. Kiểm tra

- UI: https://localhost:8080 → Applications: dev-* trỏ cluster **dev**, prod-* trỏ cluster **prod**.
- Management: `kubectl --context kind-management get pods -n argocd`
- Dev: `kubectl --context kind-dev get pods -A`
- Prod: `kubectl --context kind-prod get pods -A`

---

## Lưu ý

- Replica đã set 0 trong values (chỉ test manifest); không có pod workload chạy, tiết kiệm RAM.
- **Kind trên Linux:** Argo CD phải gọi API dev/prod qua IP host; Kind dùng network gateway **172.18.0.1** (không phải 172.17.0.1). Nếu đăng ký cluster với 172.17.0.1 sẽ bị `dial tcp ... i/o timeout`. Sửa: cập nhật secret cluster sang `server=https://172.18.0.1:30443` / `31443` (xem bước 3.3). **Nếu 172.18.0.1 vẫn timeout** (vd. firewall host): dùng IP container trực tiếp, port **6443** (không dùng host port): `docker inspect dev-control-plane --format '{{.NetworkSettings.Networks.kind.IPAddress}}'` và tương tự `prod-control-plane` → patch secret `server=https://<IP>:6443`. IP sẽ đổi nếu xóa/tạo lại cluster.
- Nếu đổi port trong `kind/*-kind-config.yaml` thì nhớ đổi cùng port trong bước 3.3.
- **Cluster thứ 3** (khi đã có 2 cluster chạy) dễ fail kubelet (connection refused :10248) do thiếu RAM → xem mục tương ứng trong **README.md** (chạy 2 cluster hoặc tăng RAM Docker).
- **meo-station-database-dev/prod:** Chart dev đã set `useEBS: false` để chạy trên Kind (default StorageClass). Trên Kind không có External Secrets → Secret `meo-stationery-database-secrets-dev` / `meo-stationery-database-secrets` không tồn tại → Pod database không start. Tạo tay trên từng cluster (ví dụ dev):
  ```bash
  kubectl --context kind-dev create namespace database --dry-run=client -o yaml | kubectl apply -f -
  kubectl --context kind-dev -n database create secret generic meo-stationery-database-secrets-dev \
    --from-literal=POSTGRES_USER=meo_admin \
    --from-literal=POSTGRES_DB=meo_stationery \
    --from-literal=POSTGRES_PASSWORD=localdev
  ```
  Sau đó bấm **SYNC** lại app trong Argo CD.
