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
# kind-staging     kind-staging     ...
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

Để Argo CD (chạy trong management) gọi được API server của dev/staging/prod, cần biết địa chỉ mạng:

- **Mac/Windows (Docker Desktop):** `host.docker.internal:<host-port>` (30443/32443/31443)
- **Linux (Kind) — khuyến nghị:** dùng **container IP trực tiếp + port 6443**. Lấy IP bằng `docker inspect <cluster>-control-plane --format '{{.NetworkSettings.Networks.kind.IPAddress}}'`. Cách này ổn định nhất, tránh lỗi `host.docker.internal` không resolve hoặc gateway timeout. IP sẽ thay đổi khi xóa/tạo lại cluster.

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

**Trên Linux** (dùng **container IP trực tiếp** + port **6443** — cách ổn định nhất, tránh lỗi `host.docker.internal` không resolve hoặc `172.18.0.1` timeout):

```bash
kubectl config use-context kind-management

DEV_IP=$(docker inspect dev-control-plane --format '{{.NetworkSettings.Networks.kind.IPAddress}}')
STAGING_IP=$(docker inspect staging-control-plane --format '{{.NetworkSettings.Networks.kind.IPAddress}}')
PROD_IP=$(docker inspect prod-control-plane --format '{{.NetworkSettings.Networks.kind.IPAddress}}')

kubectl create secret generic cluster-dev -n argocd \
  --from-literal=name=dev \
  --from-literal=server=https://$DEV_IP:6443 \
  --from-literal=config="{\"bearerToken\":\"$DEV_TOKEN\",\"tlsClientConfig\":{\"insecure\":true}}"
kubectl label secret cluster-dev -n argocd argocd.argoproj.io/secret-type=cluster

kubectl create secret generic cluster-staging -n argocd \
  --from-literal=name=staging \
  --from-literal=server=https://$STAGING_IP:6443 \
  --from-literal=config="{\"bearerToken\":\"$STAGING_TOKEN\",\"tlsClientConfig\":{\"insecure\":true}}"
kubectl label secret cluster-staging -n argocd argocd.argoproj.io/secret-type=cluster

kubectl create secret generic cluster-prod -n argocd \
  --from-literal=name=prod \
  --from-literal=server=https://$PROD_IP:6443 \
  --from-literal=config="{\"bearerToken\":\"$PROD_TOKEN\",\"tlsClientConfig\":{\"insecure\":true}}"
kubectl label secret cluster-prod -n argocd argocd.argoproj.io/secret-type=cluster
```

> **Lưu ý:** Container IP sẽ thay đổi mỗi lần xóa/tạo lại cluster Kind. Luôn chạy `docker inspect` để lấy IP mới.

---

## 4. Add repo Git và apply bootstrap (trên management)

Bootstrap gồm **4 file** trong `argocd/bootstrap/` (`01-projects` + dev + staging + prod). Apply lần lượt để tạo `argocd-projects` và các stack `dev-meostation`, `staging-meostation`, `prod-meostation`.

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
- **dev-meostation** → render chart `argocd/manifest-apps` (env=dev) → sinh ra `dev-meostation-backend-app`, `dev-meostation-database-app`, `dev-meostation-frontend-app` — mỗi app con dùng Helm chart **`template`** với `valueFiles`: `app/be.yaml` hoặc `app/db.yaml`, `env/<env>.yaml`, `config/base/config.yaml`, `config/env/<env>.yaml` → deploy lên cluster **dev**
- **staging-meostation** → tương tự, env=staging → deploy lên cluster **staging**
- **prod-meostation** → tương tự, env=prod → deploy lên cluster **prod**

> **Lưu ý:** Đối với môi trường **prod**, chính sách sync là `Manual`. Cần vào UI Argo CD (hoặc CLI) bấm Sync thủ công cho app prod.

---

## 5. Triển khai Monitoring Stack (Prometheus & Grafana)

Hệ thống sử dụng mô hình **Hub-and-Spoke**: Server tập trung tại `management` và các Agent thu thập tại các cụm workload. Cấu hình Helm values nằm tại `config/monitoring/`.

```bash
kubectl config use-context kind-management

# 1. Cài đặt Prometheus Server & Grafana trên management
kubectl apply -f argocd/bootstrap/05-monitoring-mgmt.yaml

# 2. Cài đặt các Agent thu thập trên các cụm con
kubectl apply -f argocd/bootstrap/06-monitoring-dev.yaml
kubectl apply -f argocd/bootstrap/07-monitoring-staging.yaml
kubectl apply -f argocd/bootstrap/08-monitoring-prod.yaml
```

Sau khi cài đặt, ArgoCD sẽ tự động kéo Helm chart từ `prometheus-community` và gộp với cấu hình trong `config/monitoring/`.

---

## 6. Kiểm tra

- UI ArgoCD: https://localhost:8080 → Applications: `dev-*`, `monitoring-*`...
- UI Grafana:
  ```bash
  kubectl -n monitoring port-forward svc/monitoring-management-grafana 3000:80
  # Truy cập: http://localhost:3000 (admin / admin)
  ```
- Management: `kubectl --context kind-management get pods -n monitoring`
- Dev: `kubectl --context kind-dev get pods -n monitoring`
- Staging: `kubectl --context kind-staging get pods -A`
- Prod: `kubectl --context kind-prod get pods -A`

---

## Lưu ý

- Replica count / image tag được cấu hình trong `env/<env>.yaml`. Chart workload là `template/`; profile values trong `app/be.yaml`, `app/db.yaml`; config chung `config/base/config.yaml`, override theo môi trường `config/env/<env>.yaml`. **Không** còn đường `.manifest/` trong flow Argo hiện tại.
- **Kind trên Linux:** Argo CD gọi API dev/staging/prod qua **container IP + port 6443** (xem bước 3.4). Lấy IP: `docker inspect <cluster>-control-plane --format '{{.NetworkSettings.Networks.kind.IPAddress}}'`. **KHÔNG dùng** `host.docker.internal` (không resolve trên Linux) hay gateway `172.18.0.1` (có thể timeout). IP container sẽ thay đổi khi xóa/tạo lại cluster → phải tạo lại secret.
- Nếu đổi port trong `kind/*-kind-config.yaml` thì nhớ đổi cùng port trong bước 3.4.
- **Cluster thứ 3** (khi đã có 2 cluster chạy) dễ fail kubelet (connection refused :10248) do thiếu RAM → xem mục tương ứng trong **README.md** (chạy 2 cluster hoặc tăng RAM Docker).
- **Database/backend trên Kind:** Có hai cách: **ESO + AWS Secrets Manager** (**mục 6.5.1**, khuyến nghị khi đã có secret trên AWS) hoặc **Secret tĩnh bằng kubectl** (**mục 6.5.2**, offline / không AWS). **Lưu ý:** lệnh có pipe phải có `--context` ở cả hai bên, nếu không namespace sẽ bị tạo nhầm cluster.

---

## 6. Khởi động lại môi trường Kind sau khi reboot

Kind là môi trường **ephemeral** để test. Sau khi tắt/bật máy lại **không có lệnh "start lại nguyên cụm" đơn giản**. Cách an toàn, ít lỗi nhất:

> **Xóa cụm cũ nếu còn → tạo lại 4 cluster Kind → cài lại Argo CD → đăng ký dev/staging/prod → làm lại secrets (6.5.1 ESO+AWS hoặc 6.5.2 kubectl) → sync lại app.**

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

Dùng **IP container trực tiếp** + port **6443** (cách ổn định nhất trên Linux):

```bash
kubectl config use-context kind-management

DEV_IP=$(docker inspect dev-control-plane --format '{{.NetworkSettings.Networks.kind.IPAddress}}')
STAGING_IP=$(docker inspect staging-control-plane --format '{{.NetworkSettings.Networks.kind.IPAddress}}')
PROD_IP=$(docker inspect prod-control-plane --format '{{.NetworkSettings.Networks.kind.IPAddress}}')

kubectl create secret generic cluster-dev -n argocd \
  --from-literal=name=dev \
  --from-literal=server=https://$DEV_IP:6443 \
  --from-literal=config="{\"bearerToken\":\"$DEV_TOKEN\",\"tlsClientConfig\":{\"insecure\":true}}"
kubectl label secret cluster-dev -n argocd argocd.argoproj.io/secret-type=cluster

kubectl create secret generic cluster-staging -n argocd \
  --from-literal=name=staging \
  --from-literal=server=https://$STAGING_IP:6443 \
  --from-literal=config="{\"bearerToken\":\"$STAGING_TOKEN\",\"tlsClientConfig\":{\"insecure\":true}}"
kubectl label secret cluster-staging -n argocd argocd.argoproj.io/secret-type=cluster

kubectl create secret generic cluster-prod -n argocd \
  --from-literal=name=prod \
  --from-literal=server=https://$PROD_IP:6443 \
  --from-literal=config="{\"bearerToken\":\"$PROD_TOKEN\",\"tlsClientConfig\":{\"insecure\":true}}"
kubectl label secret cluster-prod -n argocd argocd.argoproj.io/secret-type=cluster
```

### 6.5. Secrets cho database + backend (sau khi recreate cluster)

#### 6.5.1. External Secrets Operator + AWS Secrets Manager (thay cho “ESO giả”)

Dùng khi máy/cluster có egress ra AWS và bạn đã có secret JSON trên Secrets Manager (cùng keys như Terraform `modules/secrets`: `POSTGRES_*`, `DATABASE_URL`, `NEXTAUTH_SECRET`).

**Trên từng workload cluster** (`kind-dev`, `kind-staging`, `kind-prod`) — lặp lại với đúng `--context` và file values tương ứng:

1. Cài External Secrets Operator (**một lần trên mỗi** cluster `kind-dev`, `kind-staging`, `kind-prod`):

   Config Kind của repo dùng **Kubernetes 1.28** (`kindest/node:v1.28.0`). Chart ESO **≥ 0.20.1** kèm CRD có `selectableFields` (chỉ hợp lệ từ K8s ~1.31+) → `helm install` báo lỗi kiểu `.spec.versions[0].selectableFields: field not declared in schema` và **CRD không được cài** → apply `ExternalSecret` sẽ lỗi `no matches for kind "ExternalSecret"`.

   **Cách xử lý:** ghim chart **0.19.2** (bản 0.20.1 trở lên cần K8s mới hơn). Nếu lần trước cài hỏng: `helm uninstall external-secrets -n external-secrets` trên context tương ứng, rồi cài lại.

   ```bash
   helm repo add external-secrets https://charts.external-secrets.io
   helm repo update

   for ctx in kind-dev kind-staging kind-prod; do
     helm upgrade --install external-secrets external-secrets/external-secrets \
       --version 0.19.2 \
       -n external-secrets --create-namespace \
       --kube-context "$ctx"
   done
   ```

   **Sau `helm install`, bắt buộc chờ pod ESO (webhook) Ready** rồi mới apply `ClusterSecretStore` / `ExternalSecret`. Nếu apply quá sớm, API server gọi validating webhook `external-secrets-webhook` trong khi pod chưa listen → lỗi `connection refused` / `Internal error occurred: failed calling webhook`.

   ```bash
   for ctx in kind-dev kind-staging kind-prod; do
     kubectl --context "$ctx" -n external-secrets rollout status deployment/external-secrets-webhook --timeout=300s
     kubectl --context "$ctx" -n external-secrets wait --for=condition=Ready pods --all --timeout=300s
   done
   ```

   (Nếu tên deployment webhook khác: `kubectl --context kind-dev -n external-secrets get deploy`.)

   (Muốn dùng ESO mới nhất: nâng image Kind lên **≥ 1.31** trong `kind/*-kind-config.yaml` rồi bỏ `--version`.)

2. Tạo `aws-credentials` trong namespace `external-secrets` **trên từng cluster**

   **Không bỏ bước này** dù bạn đã tạo secret **trên AWS Secrets Manager** (Terraform / console) từ trước:

   - Secret **trên AWS** (`meo-stationery/dev/app-credentials` …) chứa JSON app (`POSTGRES_*`, `DATABASE_URL`, …) — đích mà **ExternalSecret** đồng bộ vào K8s.
   - Secret **`aws-credentials` trong cluster** chứa **Access key IAM** để **controller ESO** gọi API AWS (`GetSecretValue`). Không có nó (hoặc không có auth tương đương), ESO không đọc được AWS.

   IAM cần `secretsmanager:GetSecretValue` trên prefix secret của project (giống user ESO trong `terraform_secret` hoặc `terraform/modules/iam`).

   ```bash
   kubectl --context kind-dev -n external-secrets create secret generic aws-credentials \
     --from-literal=access-key-id='YOUR_AWS_ACCESS_KEY_ID' \
     --from-literal=secret-access-key='YOUR_AWS_SECRET_ACCESS_KEY'
   # Lặp với kind-staging / kind-prod (thường cùng một cặp key). Nếu secret đã tồn tại: thêm --dry-run=client -o yaml | kubectl apply -f - hoặc delete rồi create lại.
   ```

3. Tạo namespace đích (ESO ghi K8s Secret vào `database` + `meo-stationery`). Ví dụ cho **kind-dev** (đổi context cho staging/prod):

   ```bash
   kubectl --context kind-dev create namespace database --dry-run=client -o yaml | kubectl --context kind-dev apply -f -
   kubectl --context kind-dev create namespace meo-stationery --dry-run=client -o yaml | kubectl --context kind-dev apply -f -
   kubectl --context kind-prod create namespace database --dry-run=client -o yaml | kubectl --context kind-prod apply -f -
   kubectl --context kind-prod create namespace meo-stationery --dry-run=client -o yaml | kubectl --context kind-prod apply -f -
   kubectl --context kind-staging create namespace database --dry-run=client -o yaml | kubectl --context kind-staging apply -f -
   kubectl --context kind-staging create namespace meo-stationery --dry-run=client -o yaml | kubectl --context kind-staging apply -f -
   ```

4. Apply `ClusterSecretStore` + `ExternalSecret` từ repo (từ thư mục gốc repo):

   ```bash
   cd ~/Downloads/practice_RKE2   # hoặc /path/to/practice_RKE2

    # DEV
    helm template external-secrets external-secrets/applications \
      -f external-secrets/applications/values.yaml \
      -f config/base/config.yaml \
      -f config/env/dev.yaml \
      | kubectl --context kind-dev apply -f -

    # STAGING
    helm template external-secrets external-secrets/applications \
      -f external-secrets/applications/values.yaml \
      -f config/base/config.yaml \
      -f config/env/staging.yaml \
      | kubectl --context kind-staging apply -f -

    # PROD
    helm template external-secrets external-secrets/applications \
      -f external-secrets/applications/values.yaml \
      -f config/base/config.yaml \
      -f config/env/prod.yaml \
      | kubectl --context kind-prod apply -f -
   ```

5. Kiểm tra sync:

   ```bash
   kubectl --context kind-dev get externalsecret,secret -n database
   kubectl --context kind-dev get externalsecret,secret -n meo-stationery
   ```

**Staging trên AWS:** Repo có `env-secrets/staging.yaml` trỏ tới `meo-stationery/staging/app-credentials`. Terraform trong repo **chưa** có `environments/staging` — bạn cần tạo secret đó trên AWS (console hoặc thêm module) trước khi ESO sync được.

#### 6.5.2. Secret tĩnh bằng kubectl (không AWS — “giả ESO”)

Khi không dùng ESO/AWS, tạo Secret thủ công trên từng cluster. **Lưu ý:** lệnh có pipe phải có `--context` ở cả hai bên (`| kubectl --context kind-dev apply -f -`), nếu không namespace sẽ bị tạo nhầm cluster.

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

**Trên `kind-staging`:**

```bash
# DB
kubectl --context kind-staging create namespace database --dry-run=client -o yaml | kubectl --context kind-staging apply -f -
kubectl --context kind-staging -n database create secret generic meo-stationery-database-secrets-staging \
  --from-literal=POSTGRES_USER=meo_admin \
  --from-literal=POSTGRES_DB=meo_stationery \
  --from-literal=POSTGRES_PASSWORD=localstaging

# Backend
kubectl --context kind-staging create namespace meo-stationery --dry-run=client -o yaml | kubectl --context kind-staging apply -f -
kubectl --context kind-staging -n meo-stationery create secret generic meo-stationery-backend-secrets-staging \
  --from-literal=DATABASE_URL='postgresql://meo_admin:localstaging@postgres.database.svc.cluster.local:5432/meo_stationery?schema=public' \
  --from-literal=NEXTAUTH_SECRET='kind-staging-nextauth'
```

**Trên `kind-prod`:** (**phải** có `--context kind-prod` ở cả hai bên pipe):

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

Bootstrap là các file Application; apply lần lượt:

```bash
kubectl config use-context kind-management
cd ~/Downloads/practice_RKE2

argocd repo add https://github.com/minhtri1612/learning_RKE2.git

# 1. App meostation
kubectl apply -f argocd/bootstrap/01-projects.yaml
kubectl apply -f argocd/bootstrap/02-dev-meostation-stack.yaml
kubectl apply -f argocd/bootstrap/03-staging-meostation-stack.yaml
kubectl apply -f argocd/bootstrap/04-prod-meostation-stack.yaml

# 2. App Monitoring
kubectl apply -f argocd/bootstrap/05-monitoring-mgmt.yaml
kubectl apply -f argocd/bootstrap/06-monitoring-dev.yaml
kubectl apply -f argocd/bootstrap/07-monitoring-staging.yaml
kubectl apply -f argocd/bootstrap/08-monitoring-prod.yaml
```

Sau khi sync xong, sẽ có:

- `argocd-projects` → tạo AppProject dev, staging, prod
- `dev-meostation` → render `argocd/manifest-apps` → sinh ra `dev-meostation-backend-app`, `dev-meostation-database-app`, `dev-meostation-frontend-app` (chart `template` + `app/*.yaml` + `env/` + `config/`)
- `staging-meostation` → sinh ra `staging-meostation-backend-app`, `staging-meostation-database-app`, `staging-meostation-redis-app` (nếu `env/staging.yaml` khai báo `redis`)
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

---

### 6.7. Gỡ rối thường gặp (đọc trước khi blame doc)

**Hai “nguồn sự thật” — đừng trộn lung tung**

- **Argo CD** (app con `dev-meostation-*-app`) đã cấu hình `helm.releaseName` = `backend` / `database` / `frontend` và sync chart `template` lên **kind-dev** (hoặc staging/prod).  
- **Helm CLI** `helm upgrade --install backend ...` trên **cùng** cluster/namespace với cùng tên release → Kubernetes **server-side apply** sẽ báo **conflict với `argocd-controller`** (Deployment/StatefulSet).  
- **Khuyến nghị:** workload app chỉ để **Argo sync** từ Git; chỉ dùng Helm tay khi bạn đã **suspend** app con tương ứng trên Argo (context **`kind-management`**, namespace `argocd`). Nếu đã lỡ cài Helm failed: `helm uninstall backend -n meo-stationery` và `helm uninstall database -n database`, rồi bật lại sync Argo.

**Context đúng cho từng việc**

- CRD `Application` (Argo) chỉ có trên cluster cài Argo → **`kubectl ... application ...` dùng `--context kind-management`**, **không** dùng `kind-dev`.
- Pod/Secret/ConfigMap trên workload cluster → **`kind-dev` / `kind-staging` / `kind-prod`**.
- Lệnh **Helm** trỏ cluster bằng **`--kube-context kind-dev`**, không có flag `--context` (đó là của `kubectl`).

**External Secrets chart trong repo (không còn file cũ)**

- Apply manifest ESO **không** dùng các file `-secrets.yaml` lẻ tẻ. Luôn dùng:
  - `external-secrets/applications/values.yaml`
  - `config/base/config.yaml` (Chứa danh sách key secret)
  - `config/env/dev.yaml` | `staging.yaml` | `prod.yaml` (Chứa path metadata)
- Mỗi env chỉ cần chạy **một** lệnh `helm template ... | kubectl apply` tổng thể thay vì chia ra backend/database profile.

**Pod `ContainerCreating` + `configmap "backend-config" not found`**

- Chart `template` chỉ tạo ConfigMap khi **có** `runtimeConfig.enabled` **và** `runtimeConfig.data` (xem `template/templates/configmap.yaml`). `app/be.yaml` / `app/db.yaml` trong repo này đã có `data` — nếu trên cluster vẫn không thấy ConfigMap, gần như chắc **Argo đang sync revision Git cũ** (bootstrap trỏ `https://github.com/minhtri1612/learning_RKE2.git` `main` — phải **push** đúng repo/branch đó). Sau khi push: Refresh + Sync app trên Argo.
- Từ bản chart đã cập nhật: Deployment/StatefulSet **chỉ mount** volume `app-config` khi có `runtimeConfig.data` (khớp điều kiện tạo ConfigMap) — tránh pod kẹt vĩnh viễn khi Git chưa có `data` (pod có thể lên nhưng thiếu file config cho tới khi bạn sync đúng Git).

**ExternalSecret database `SecretSyncedError`**

- Kiểm tra `config/env/<env>.yaml`: `database.secrets.remoteKey` phải **trùng tên secret thật** trên AWS. Nếu Terraform chỉ tạo một JSON `.../app-credentials`, đừng trỏ DB sang `.../database` khi secret đó chưa tồn tại.

**ServiceAccount “exists and cannot be imported into the current release”**

- Tài nguyên đã được tạo trước đó không thuộc Helm release hiện tại. Trên môi trường practice: ưu tiên **một** luồng (Argo **hoặc** Helm tay); tránh vừa Argo vừa `helm upgrade` cùng release.
