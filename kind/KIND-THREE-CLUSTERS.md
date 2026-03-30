# (Hiện tại) 4 cluster Kind (management + dev + staging + prod) – giống cloud

Argo CD cài **chỉ** trên **cluster management**. Deploy app dev sang cluster **dev**, app staging sang cluster **staging**, app prod sang cluster **prod**. Cần expose API server của dev/staging/prod ra host để Argo CD (chạy trong management) gọi được.

---

## 1. Tạo 4 cluster Kind

**Bắt buộc chạy từ thư mục gốc repo** (nếu đang ở `~` sẽ lỗi `open kind/management-kind-config.yaml: no such file or directory`):

```bash
cd ~/Downloads/practice_RKE2   # hoặc cd /path/to/practice_RKE2

kind create cluster --name management --config kind/management-kind-config.yaml
kind create cluster --name dev        --config kind/dev-kind-config.yaml
kind create cluster --name staging    --config kind/staging-kind-config.yaml
kind create cluster --name prod       --config kind/prod-kind-config.yaml
```

- **management**: API server trên host tại `127.0.0.1:33443` (Argo CD chạy ở đây)
- **dev**: API server trên host tại `127.0.0.1:30443`
- **staging**: API server trên host tại `127.0.0.1:32443`
- **prod**: API server trên host tại `127.0.0.1:31443`

Kiểm tra:

```bash
kubectl config get-contexts
# kind-management  kind-management  ...
# kind-dev         kind-dev         ...
# kind-prod        kind-prod        ...
```

**Nếu `kubectl` báo lỗi TLS** (`x509: certificate is valid for ..., not 0.0.0.0`): kubeconfig đang trỏ server `0.0.0.0` — certificate API server không có SAN đó. **Chạy ngay** (trước bước 2) để trỏ cluster sang `127.0.0.1`:

```bash
kubectl config set-cluster kind-management --server=https://127.0.0.1:33443
kubectl config set-cluster kind-dev --server=https://127.0.0.1:30443
kubectl config set-cluster kind-staging --server=https://127.0.0.1:32443
kubectl config set-cluster kind-prod --server=https://127.0.0.1:31443
```

---

## 2. Cài Argo CD trên cluster management

```bash
kubectl config use-context kind-management

kubectl create namespace argocd
kubectl apply --server-side --force-conflicts -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

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

**Lưu ý khi vừa recreate ArgoCD (xóa/tạo lại cluster):** token của `argocd` CLI cũ sẽ lỗi kiểu `invalid session: token signature is invalid`.
Fix nhanh: xóa config cũ và login lại:

```bash
rm -rf ~/.argocd
PASS=$(kubectl --context kind-management -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)
argocd login localhost:8080 --insecure --username admin --password "$PASS"
```

---

## 3. Đăng ký cluster "dev", "staging" và "prod" với Argo CD (trên management)

Argo CD chạy **trong** cluster management.

- **Cluster management**: Argo CD tự deploy vào chính cluster này qua `https://kubernetes.default.svc` (không cần "register" gì thêm).
- **Cluster dev/staging/prod**: để Argo CD deploy sang 3 cluster này, cần **đăng ký** credentials cho dev/staging/prod.

Để Argo CD (chạy trong management) gọi được API server của dev/prod, từ pod trong management, địa chỉ "máy host" là:

- **Mac/Windows (Docker Desktop):** `host.docker.internal`
- **Linux (Kind):** dùng **`172.18.0.1`** — Kind tạo network `kind` với gateway 172.18.0.1; từ pod trong management phải dùng IP này để ra host (port 30443/31443). Nếu dùng `172.17.0.1` sẽ bị **dial tcp ... i/o timeout**.

Dev API = `https://<host>:30443`, Staging API = `https://<host>:32443`, Prod API = `https://<host>:31443`.

### 3.1. Tạo ServiceAccount và token trên cluster dev

```bash
kubectl --context kind-dev apply -f kind/dev-argocd-manager.yaml
sleep 5
```

Lấy token dev (giữ nguyên terminal để dùng biến `$DEV_TOKEN` ở bước 3.4):

```bash
DEV_TOKEN=$(kubectl --context kind-dev get secret argocd-manager-long-lived-token -n kube-system -o jsonpath='{.data.token}' | base64 -d)
echo "$DEV_TOKEN"
```

### 3.2. Tạo ServiceAccount và token trên cluster prod

```bash
kubectl --context kind-prod apply -f kind/prod-argocd-manager.yaml
sleep 5
```

Lấy token prod (giữ nguyên terminal để dùng biến `$PROD_TOKEN` ở bước 3.4):

```bash
PROD_TOKEN=$(kubectl --context kind-prod get secret argocd-manager-long-lived-token -n kube-system -o jsonpath='{.data.token}' | base64 -d)
echo "$PROD_TOKEN"
```

### 3.3. Tạo ServiceAccount và token trên cluster staging

```bash
kubectl --context kind-staging apply -f kind/dev-argocd-manager.yaml
sleep 5
```

Lấy token staging (giữ nguyên terminal để dùng biến `$STAGING_TOKEN` ở bước 3.4):

```bash
STAGING_TOKEN=$(kubectl --context kind-staging get secret argocd-manager-long-lived-token -n kube-system -o jsonpath='{.data.token}' | base64 -d)
echo "$STAGING_TOKEN"
```

### 3.4. Tạo Secret cluster "dev", "staging" và "prod" trong Argo CD (trên management)

Chạy **cùng shell** sau khi đã chạy 3.1, 3.2 và 3.3 (để có biến `$DEV_TOKEN`, `$STAGING_TOKEN`, `$PROD_TOKEN`).

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

kubectl create secret generic cluster-staging \
  -n argocd \
  --from-literal=name=staging \
  --from-literal=server=https://host.docker.internal:32443 \
  --from-literal=config="{\"bearerToken\":\"$STAGING_TOKEN\",\"tlsClientConfig\":{\"insecure\":true}}"
kubectl label secret cluster-staging -n argocd argocd.argoproj.io/secret-type=cluster
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

kubectl create secret generic cluster-staging \
  -n argocd \
  --from-literal=name=staging \
  --from-literal=server=https://172.18.0.1:32443 \
  --from-literal=config="{\"bearerToken\":\"$STAGING_TOKEN\",\"tlsClientConfig\":{\"insecure\":true}}"
kubectl label secret cluster-staging -n argocd argocd.argoproj.io/secret-type=cluster
```

---

## 4. Add repo Git và apply bootstrap (trên management)

Bootstrap là **3 file Application** trong `argocd/bootstrap/`. Apply lần lượt để tạo Application `argocd-projects` + `dev-meostation` + `prod-meostation`.

```bash
kubectl config use-context kind-management
cd ~/Downloads/practice_RKE2   # hoặc /path/to/practice_RKE2

argocd login localhost:8080 --insecure --username admin --password "<admin_password>"
argocd repo add https://github.com/minhtri1612/learning_RKE2.git

# Apply projects trước, rồi stack (dev / staging / prod tùy nhu cầu)
kubectl apply -f argocd/bootstrap/01-projects.yaml
kubectl apply -f argocd/bootstrap/02-dev-meostation-stack.yaml
kubectl apply -f argocd/bootstrap/03-staging-meostation-stack.yaml
kubectl apply -f argocd/bootstrap/04-prod-meostation-stack.yaml
```

Sau khi sync xong, sẽ có:

- **argocd-projects** → deploy `argocd/projects` → tạo AppProject `dev`, `staging`, `prod`
- **dev-meostation** → deploy `argocd/meo-station` + env dev → sinh ra `dev-meostation-backend-app`, `dev-meostation-database-app` (cluster **dev**)
- **staging-meostation** → tương tự, `env/staging.yaml` + cluster **staging**
- **prod-meostation** → deploy `argocd/meo-station` + env prod → sinh ra `prod-meostation-backend-app`, `prod-meostation-database-app` (cluster **prod**)

> **Lưu ý:** Đối với môi trường **prod**, chính sách sync là `Manual`. Cần vào UI Argo CD (hoặc CLI) bấm Sync thủ công cho app prod.

---

## 5. Kiểm tra

- UI: https://localhost:8080 → Applications: `dev-*` trỏ cluster **dev**, `staging-*` trỏ cluster **staging**, `prod-*` trỏ cluster **prod**.
- Management: `kubectl --context kind-management get pods -n argocd`
- Dev: `kubectl --context kind-dev get pods -A`
- Staging: `kubectl --context kind-staging get pods -A`
- Prod: `kubectl --context kind-prod get pods -A`

---

## Lưu ý

- Replica đã set 0 trong values (chỉ test manifest); không có pod workload chạy, tiết kiệm RAM.
- **Kind trên Linux:** Argo CD phải gọi API dev/staging/prod qua IP host; Kind dùng network gateway **172.18.0.1** (không phải 172.17.0.1). Nếu đăng ký cluster với 172.17.0.1 sẽ bị `dial tcp ... i/o timeout`. Sửa: cập nhật secret cluster sang `server=https://172.18.0.1:30443` / `32443` / `31443` (xem bước 3.4). **Nếu 172.18.0.1 vẫn timeout** (vd. firewall host): dùng IP container trực tiếp, port **6443** (không dùng host port): `docker inspect dev-control-plane --format '{{.NetworkSettings.Networks.kind.IPAddress}}'` và tương tự `prod-control-plane` → patch secret `server=https://<IP>:6443`. IP sẽ đổi nếu xóa/tạo lại cluster.
- Nếu đổi port trong `kind/*-kind-config.yaml` thì nhớ đổi cùng port trong bước 3.4.
- **Cluster thứ 3** (khi đã có 2 cluster chạy) dễ fail kubelet (connection refused :10248) do thiếu RAM → xem mục tương ứng trong **README.md** (chạy 2 cluster hoặc tăng RAM Docker).
- **Database/backend trong các app dev/prod (vd. `dev-meostation-database-app`, `prod-meostation-backend-app`):** Chart dev đã set `useEBS: false` để chạy trên Kind (default StorageClass `local-path`). Trên Kind không có External Secrets Operator → Secret `meo-stationery-database-secrets-dev` / `meo-stationery-database-secrets` và `meo-stationery-backend-secrets-dev` / `meo-stationery-backend-secrets` không tồn tại → Pod database/backend không start. Tạo tay trên từng cluster theo mục 6.5. **Lưu ý:** lệnh có pipe phải có `--context` ở cả hai bên, nếu không namespace sẽ bị tạo nhầm cluster (vd. management).

  **Trên `kind-dev`:**
  ```bash
  kubectl --context kind-dev create namespace database --dry-run=client -o yaml | kubectl --context kind-dev apply -f -
  kubectl --context kind-dev -n database create secret generic meo-stationery-database-secrets-dev \
    --from-literal=POSTGRES_USER=meo_admin \
    --from-literal=POSTGRES_DB=meo_stationery \
    --from-literal=POSTGRES_PASSWORD=localdev
  ```
  **Trên `kind-prod`:** đổi context và tên secret (xem mục 6.5). Sau đó bấm **SYNC** lại app trong Argo CD.

---

## 6. Khởi động lại môi trường Kind sau khi reboot

Kind là môi trường **ephemeral** để test. Sau khi tắt/bật máy lại **không có lệnh "start lại nguyên cụm" đơn giản**. Cách an toàn, ít lỗi nhất:

> **Xóa cụm cũ nếu còn → tạo lại 3 cluster Kind → cài lại Argo CD → đăng ký dev/prod → tạo lại secrets local → sync lại app.**

Giả sử đang ở branch `kind` của repo này.

### 6.1. Xóa 4 cluster cũ (nếu còn)

```bash
kind delete cluster --name management
kind delete cluster --name dev
kind delete cluster --name staging
kind delete cluster --name prod
```

Không sao cả: mọi config cho Kind đã nằm trong Git (branch `kind`).

### 6.2. Tạo lại 4 cluster Kind

```bash
cd ~/Downloads/practice_RKE2   # bắt buộc từ thư mục repo

kind create cluster --name management --config kind/management-kind-config.yaml
kind create cluster --name dev        --config kind/dev-kind-config.yaml
kind create cluster --name staging    --config kind/staging-kind-config.yaml
kind create cluster --name prod       --config kind/prod-kind-config.yaml

kubectl config get-contexts   # phải thấy kind-management, kind-dev, kind-staging, kind-prod
```

**Nếu kubectl báo lỗi TLS** (x509: certificate ... not 0.0.0.0), chạy ngay:

```bash
kubectl config set-cluster kind-management --server=https://127.0.0.1:33443
kubectl config set-cluster kind-dev --server=https://127.0.0.1:30443
kubectl config set-cluster kind-staging --server=https://127.0.0.1:32443
kubectl config set-cluster kind-prod --server=https://127.0.0.1:31443
```

### 6.3. Cài lại Argo CD trên `management`

```bash
kubectl config use-context kind-management

kubectl create namespace argocd
kubectl apply --server-side --force-conflicts -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

kubectl -n argocd wait --for=condition=Ready pods --all --timeout=300s
```

Lấy lại password admin + port-forward:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d && echo
kubectl -n argocd port-forward svc/argocd-server 8080:443
```

**Quan trọng (khi chạy lại từ mục 6 sau reboot):** `argocd` CLI có thể vẫn giữ token cũ → lỗi kiểu:
`invalid session: token signature is invalid`.
Sau khi cài lại Argo CD (mục 6.3) **hãy reset token và login lại** trước khi chạy các lệnh `argocd ...`:

```bash
rm -rf ~/.argocd
PASS=$(kubectl --context kind-management -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)
argocd login localhost:8080 --insecure --username admin --password "$PASS"
```

### 6.4. Đăng ký lại cluster `dev` + `staging` + `prod` cho Argo CD

Trên `kind-dev`, `kind-staging` và `kind-prod`:

```bash
kubectl --context kind-dev  apply -f kind/dev-argocd-manager.yaml
kubectl --context kind-staging apply -f kind/dev-argocd-manager.yaml
kubectl --context kind-prod apply -f kind/prod-argocd-manager.yaml
sleep 5

DEV_TOKEN=$(kubectl --context kind-dev  get secret argocd-manager-long-lived-token -n kube-system -o jsonpath='{.data.token}' | base64 -d)
STAGING_TOKEN=$(kubectl --context kind-staging get secret argocd-manager-long-lived-token -n kube-system -o jsonpath='{.data.token}' | base64 -d)
PROD_TOKEN=$(kubectl --context kind-prod get secret argocd-manager-long-lived-token -n kube-system -o jsonpath='{.data.token}' | base64 -d)
```

Ví dụ dùng **IP container trực tiếp** (dev/prod control-plane) và port 6443:

```bash
kubectl config use-context kind-management

DEV_IP=$(docker inspect dev-control-plane --format '{{.NetworkSettings.Networks.kind.IPAddress}}')
PROD_IP=$(docker inspect prod-control-plane --format '{{.NetworkSettings.Networks.kind.IPAddress}}')

kubectl create secret generic cluster-dev -n argocd \
  --from-literal=name=dev \
  --from-literal=server=https://$DEV_IP:6443 \
  --from-literal=config="{\"bearerToken\":\"$DEV_TOKEN\",\"tlsClientConfig\":{\"insecure\":true}}"
kubectl label secret cluster-dev -n argocd argocd.argoproj.io/secret-type=cluster

kubectl create secret generic cluster-prod -n argocd \
  --from-literal=name=prod \
  --from-literal=server=https://$PROD_IP:6443 \
  --from-literal=config="{\"bearerToken\":\"$PROD_TOKEN\",\"tlsClientConfig\":{\"insecure\":true}}"
kubectl label secret cluster-prod -n argocd argocd.argoproj.io/secret-type=cluster
```

(Hoặc dùng gateway `172.18.0.1:<host-port>` như phần 3.3 nếu phù hợp máy của bạn.)

### 6.5. Tạo lại secrets local cho database + backend (giả ESO)

Vì cluster Kind mới hoàn toàn nên các Secret giả ESO phải tạo lại. **Lưu ý:** lệnh có pipe phải có `--context` ở cả hai bên (`| kubectl --context kind-dev apply -f -`), nếu không namespace sẽ bị tạo nhầm cluster.

**Trên `kind-dev`:**

```bash
# DB
kubectl --context kind-dev create namespace database --dry-run=client -o yaml | kubectl --context kind-dev apply -f -
kubectl --context kind-dev -n database create secret generic meo-stationery-database-secrets-dev \
  --from-literal=POSTGRES_USER=meo_admin \
  --from-literal=POSTGRES_DB=meo_stationery \
  --from-literal=POSTGRES_PASSWORD=localdev

# Backend
kubectl --context kind-dev create namespace meo-stationery --dry-run=client -o yaml | kubectl --context kind-dev apply -f -
kubectl --context kind-dev -n meo-stationery create secret generic meo-stationery-backend-secrets-dev \
  --from-literal=DATABASE_URL='postgresql://meo_admin:localdev@postgres.database.svc.cluster.local:5432/meo_stationery?schema=public' \
  --from-literal=NEXTAUTH_SECRET='kind-dev-nextauth'
```

**Trên `kind-prod`:** tương tự nhưng dùng secret prod (và **phải** có `--context kind-prod` ở cả hai bên pipe):

```bash
# DB
kubectl --context kind-prod create namespace database --dry-run=client -o yaml | kubectl --context kind-prod apply -f -
kubectl --context kind-prod -n database create secret generic meo-stationery-database-secrets \
  --from-literal=POSTGRES_USER=meo_admin \
  --from-literal=POSTGRES_DB=meo_stationery \
  --from-literal=POSTGRES_PASSWORD=localprod

# Backend
kubectl --context kind-prod create namespace meo-stationery --dry-run=client -o yaml | kubectl --context kind-prod apply -f -
kubectl --context kind-prod -n meo-stationery create secret generic meo-stationery-backend-secrets \
  --from-literal=DATABASE_URL='postgresql://meo_admin:localprod@postgres.database.svc.cluster.local:5432/meo_stationery?schema=public' \
  --from-literal=NEXTAUTH_SECRET='kind-prod-nextauth'
```

### 6.6. Apply lại bootstrap Argo CD

Bootstrap là 3 file Application; apply lần lượt:

```bash
kubectl config use-context kind-management
cd ~/Downloads/practice_RKE2

argocd repo add https://github.com/minhtri1612/learning_RKE2.git

kubectl apply -f argocd/bootstrap/01-projects.yaml
kubectl apply -f argocd/bootstrap/02-dev-meostation-stack.yaml
kubectl apply -f argocd/bootstrap/03-staging-meostation-stack.yaml
kubectl apply -f argocd/bootstrap/04-prod-meostation-stack.yaml
```

Sau khi sync xong, sẽ có:

- `argocd-projects` → tạo AppProject dev, staging, prod
- `dev-meostation` → sinh ra `dev-meostation-backend-app`, `dev-meostation-database-app`
- `staging-meostation` → sinh ra `staging-meostation-*-app`
- `prod-meostation` → sinh ra `prod-meostation-backend-app`, `prod-meostation-database-app`

Với môi trường **prod** (sync policy `Manual`), force sync thủ công:

```bash
argocd app sync argocd/prod-meostation
argocd app sync argocd/prod-meostation-backend-app
argocd app sync argocd/prod-meostation-database-app
```

> **Lưu ý:** Nếu ArgoCD CLI báo `permission denied`, login lại trước:
> ```bash
> rm -rf ~/.argocd
> PASS=$(kubectl --context kind-management -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)
> argocd login localhost:8080 --insecure --username admin --password "$PASS"
> ```
