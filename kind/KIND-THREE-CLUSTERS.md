# Kind — khởi động lại mỗi ngày (sau reboot)

Luồng **chính** trong tài liệu này: xoá / tạo lại 4 cluster (management + dev + staging + prod), Helm Cilium trên management, Argo CD, đăng ký cluster workload, secrets, bootstrap GitOps, Gateway/Cilium trên dev–staging–prod.

**Chạy lệnh từ thư mục gốc repo** (`cd ~/Downloads/practice_RKE2` hoặc path tương đương). Argo CD chỉ trên **kind-management**. API từ máy host: management `127.0.0.1:33443`, dev `30443`, staging `32443`, prod `31443`.

---

## 1. Khởi động lại môi trường Kind (sau reboot / mỗi ngày)

Kind là môi trường **ephemeral** để test. Sau khi tắt/bật máy lại **không có lệnh "start lại nguyên cụm" đơn giản**. Cách an toàn, ít lỗi nhất:

> **Xóa cụm cũ (nếu còn) → tạo lại Kind (management + Helm Cilium → dev/staging/prod) → Argo CD → đăng ký cluster → secrets (1.5.1 ESO hoặc 1.5.2 kubectl) → bootstrap Argo → sync app.**

Giả sử đang ở branch `kind` của repo này.

### 1.1. Xóa 4 cluster cũ (nếu còn)

```bash
kind delete cluster --name management
kind delete cluster --name dev
kind delete cluster --name staging
kind delete cluster --name prod
```

Không sao cả: mọi config cho Kind đã nằm trong Git (branch `kind`).

### 1.2. Tạo lại 4 cluster Kind

Tạo **management** trước, **Helm Cilium** ngay (sau khi chỉnh kubeconfig), rồi **dev / staging / prod**.

```bash
cd ~/Downloads/practice_RKE2   # bắt buộc từ thư mục repo

kind create cluster --name management --config kind/management-kind-config.yaml

kubectl config use-context kind-management
# Bắt buộc trước helm (tránh TLS 0.0.0.0 và tránh cài Argo khi chưa có CNI)
kubectl config set-cluster kind-management --server=https://127.0.0.1:33443

helm repo add cilium https://helm.cilium.io 2>/dev/null || true
helm repo update
# Lần đầu: chưa có CRD ServiceMonitor (Prometheus Operator) → phải tắt ServiceMonitor trong chart, nếu không Helm lỗi
# "no matches for kind ServiceMonitor" và Cilium không cài → không CNI → Argo CD Pending.
helm upgrade --install cilium cilium/cilium -n kube-system --create-namespace \
  --version 1.19.2 \
  -f cilium/cilium-values-management.yaml \
  -f cilium/cilium-values-management-bootstrap.yaml \
  --wait --timeout 15m

kind create cluster --name dev        --config kind/dev-kind-config.yaml
kind create cluster --name staging    --config kind/staging-kind-config.yaml
kind create cluster --name prod       --config kind/prod-kind-config.yaml

kubectl config set-cluster kind-dev --server=https://127.0.0.1:30443
kubectl config set-cluster kind-staging --server=https://127.0.0.1:32443
kubectl config set-cluster kind-prod --server=https://127.0.0.1:31443
# hoặc: bash scripts/kind-fix-kubeconfig-servers.sh

kubectl config get-contexts   # phải thấy kind-management, kind-dev, kind-staging, kind-prod
```

CIDR pod/service: file `kind/*-kind-config.yaml` (không trùng giữa cụm). Kubeconfig: **mục 1.2** (`127.0.0.1` trước Helm).

**Nếu vẫn lỗi TLS** sau khi đã tạo lại cluster: chạy `bash scripts/kind-fix-kubeconfig-servers.sh` hoặc bốn lệnh `kubectl config set-cluster` như **mục 1.2**.

### 1.3. Cài lại Argo CD trên `management`

Chỉ khi **Cilium đã Ready** trên `kind-management` (mục 1.2). Nếu bỏ qua Helm / lỗi TLS, pod Argo sẽ **Pending**.

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

**Quan trọng (mỗi lần recreate Argo CD):** `argocd` CLI có thể vẫn giữ token cũ → lỗi kiểu:
`invalid session: token signature is invalid`.
Sau khi cài lại Argo CD (mục 1.3) **hãy reset token và login lại** trước khi chạy các lệnh `argocd ...`:

```bash
rm -rf ~/.argocd
PASS=$(kubectl --context kind-management -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)
argocd login localhost:8080 --insecure --username admin --password "$PASS"
```

### 1.4. Đăng ký lại cluster `dev` + `staging` + `prod` cho Argo CD

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

### 1.5. Secrets cho database + backend (sau khi recreate cluster)

#### 1.5.1. External Secrets Operator + AWS Secrets Manager (thay cho “ESO giả”)

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

#### 1.5.2. Secret tĩnh bằng kubectl (không AWS — “giả ESO”)

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

### 1.6. Apply lại bootstrap Argo CD

Bootstrap là các file Application; apply lần lượt:

```bash
kubectl config use-context kind-management
cd ~/Downloads/practice_RKE2

argocd repo add https://github.com/minhtri1612/learning_RKE2.git
argocd repo add https://argoproj.github.io/argo-helm --type helm --name argo-helm
argocd repo add https://metallb.github.io/metallb --type helm --name metallb
argocd repo add https://helm.cilium.io/ --type helm --name cilium

# 1. App meostation
kubectl apply -f argocd/bootstrap/01-projects.yaml
kubectl apply -f argocd/bootstrap/02-dev-meostation-stack.yaml
kubectl apply -f argocd/bootstrap/03-staging-meostation-stack.yaml
kubectl apply -f argocd/bootstrap/04-prod-meostation-stack.yaml

# 2. App Monitoring
kubectl apply -f argocd/bootstrap/05-monitoring-mgmt.yaml
kubectl apply -f argocd/bootstrap/18-cilium-management.yaml
kubectl apply -f argocd/bootstrap/06-monitoring-dev.yaml
kubectl apply -f argocd/bootstrap/07-monitoring-staging.yaml
kubectl apply -f argocd/bootstrap/08-monitoring-prod.yaml

# Monitoring: sau mỗi lần recreate Kind — remote_write → xem mục 1.6.1 trong KIND-THREE-CLUSTERS.md (đừng bỏ qua).

# 2b. Argo Rollouts (backend dùng Rollout / AnalysisTemplate)
kubectl apply -f argocd/bootstrap/12-argo-rollouts-dev.yaml
kubectl apply -f argocd/bootstrap/13-argo-rollouts-staging.yaml
kubectl apply -f argocd/bootstrap/14-argo-rollouts-prod.yaml

# 3. App Cilium (nhớ peer IP hub — scripts/kind-clustermesh-peer-ip.sh; commit/push `cilium/clustermesh-management-peer.yaml` nếu Argo dùng remote)
kubectl apply -f argocd/bootstrap/09-cilium-dev.yaml
kubectl apply -f argocd/bootstrap/10-cilium-staging.yaml
kubectl apply -f argocd/bootstrap/11-cilium-prod.yaml

# 4. MetalLB (LoadBalancer Kind)
kubectl apply -f argocd/bootstrap/01-projects.yaml
kubectl apply -f argocd/bootstrap/15-metallb-dev.yaml
kubectl apply -f argocd/bootstrap/16-metallb-staging.yaml
kubectl apply -f argocd/bootstrap/17-metallb-prod.yaml
```

#### 1.6.1. Monitoring `remote_write` — script `scripts/sync-monitoring-remote-write-url.sh` (**bắt buộc đọc sau recreate Kind**)

Prometheus trên **management** nhận series từ **Prometheus Agent** trên dev/staging/prod qua `remote_write`. URL ghi trong `monitoring/monitoring-workload.yaml` (`prometheus.prometheusSpec.remoteWrite[0].url`) phải là:

`http://<IP-container-management-control-plane>:32090/api/v1/write`

(32090 = NodePort Prometheus trên management, xem `monitoring/monitoring-mgmt.yaml`.)

**Sau mỗi lần** `kind delete` / `kind create` lại cluster **management** (hoặc cả bộ lab), IP container `management-control-plane` trên mạng Docker `kind` **đổi**. Nếu Git vẫn để `127.0.0.1` hoặc IP cũ → agent trên workload **không push** được; Grafana trên management **không** có (hoặc thiếu) series theo label `cluster` / `environment` — dễ đi lạc debug chỗ khác.

**Quy trình chuẩn — copy paste từng khối (đừng bỏ bước):**

1. Trên Argo: app **`monitoring-management` (bootstrap 05)** phải **Healthy** (Prometheus management + NodePort **32090**). Cùng lúc có thể cần chỉnh `cilium/clustermesh-management-peer.yaml` (`bash scripts/kind-clustermesh-peer-ip.sh` rồi commit/push) nếu dùng ClusterMesh từ Git.

2. Vào **thư mục gốc repo** (nơi có `monitoring/`, `scripts/`):

```bash
cd ~/Downloads/practice_RKE2   # đổi đúng path máy bạn
```

3. **Quyền thực thi script** (lần đầu hoặc nếu gặp `permission denied`):

```bash
chmod +x scripts/sync-monitoring-remote-write-url.sh
# (tuỳ chọn, lưu mode vào git) git add --chmod=+x scripts/sync-monitoring-remote-write-url.sh
```

4. **Ghi URL `remote_write`** vào `monitoring/monitoring-workload.yaml` (đọc IP từ `docker inspect management-control-plane`; có `yq` thì dùng `yq`, không thì `sed`):

```bash
./scripts/sync-monitoring-remote-write-url.sh
```

5. **Kiểm tra Prometheus management** từ máy host (mong đợi `HTTP 200`):

```bash
./scripts/sync-monitoring-remote-write-url.sh --check
```

6. **Đẩy lên Git** (bắt buộc nếu Argo trỏ remote như bootstrap `learning_RKE2` / `main`) — chọn **một** trong hai cách:

   **Cách A — một lệnh (sau bước 5; script **ghi lại** file rồi `git add` → `commit` chỉ khi có diff → `push`):**

```bash
./scripts/sync-monitoring-remote-write-url.sh --commit-push
```

   (Nếu URL không đổi, không tạo commit rỗng; `git push` vẫn chạy — thường báo *up to date*. Đã làm bước 4+5 rồi thì **cách B** cũng đủ, không bắt buộc chạy thêm `--commit-push`.)

   **Cách B — tay (review diff trước khi push):**

```bash
git add monitoring/monitoring-workload.yaml
git status
git commit -m "chore(monitoring): sync remote_write URL for Kind"
git push
```

7. Trên Argo (context **kind-management**): **Refresh + Sync** `monitoring-dev`, `monitoring-staging`, `monitoring-prod` (prod **Manual** trong bootstrap thì sync tay).

```bash
kubectl config use-context kind-management
argocd app sync monitoring-dev
argocd app sync monitoring-staging
argocd app sync monitoring-prod
```

**Một dải lệnh copy paste (đủ bước 2→7, sau khi `monitoring-management` đã Healthy):**

```bash
cd ~/Downloads/practice_RKE2
chmod +x scripts/sync-monitoring-remote-write-url.sh
./scripts/sync-monitoring-remote-write-url.sh
./scripts/sync-monitoring-remote-write-url.sh --check
git add monitoring/monitoring-workload.yaml
git commit -m "chore(monitoring): sync remote_write URL for Kind" || true
git push
kubectl config use-context kind-management
argocd app sync monitoring-dev
argocd app sync monitoring-staging
argocd app sync monitoring-prod
```

*(Nếu không có thay đổi so với commit trước, `git commit` báo lỗi “nothing to commit” — `|| true` để dải lệnh không dừng; `git push` vẫn chạy. Muốn chắc chắn có commit: dùng cách A `./scripts/sync-monitoring-remote-write-url.sh --commit-push` **thay cho** ba lệnh `git` ở trên — lệnh đó vừa ghi file vừa `add`/`commit` chỉ khi có diff rồi `push`.)*

**Lệnh phụ (tuỳ chọn):**

```bash
./scripts/sync-monitoring-remote-write-url.sh --print-only   # chỉ in URL write, không sửa file
```

**Override khi không dùng Docker / tên container khác:**

- `MGMT_PROMETHEUS_REMOTE_WRITE_URL='http://IP:32090/api/v1/write' ./scripts/sync-monitoring-remote-write-url.sh`
- `MGMT_CONTROL_PLANE_CONTAINER=...` — tên container control-plane management.
- `MONITORING_WORKLOAD_VALUES=...` — đường dẫn tương đối repo tới file values workload (mặc định `monitoring/monitoring-workload.yaml`).

**Không cần** chạy lại toàn bộ bước trên mỗi ngày nếu **không** recreate Kind và remote_write vẫn đúng. Trên **RKE2 / cloud** thường dùng hostname hoặc IP cố định — có thể ghi URL ổn định trong Git, không phụ thuộc script Docker.

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

### 1.7. Cài Cilium + Gateway API cho dev/staging/prod (chuẩn bị canary theo HTTPRoute)

Mục tiêu của bước này:

- Cài Cilium CNI trên các workload cluster (`kind-dev`, `kind-staging`, `kind-prod`).
- Bật Gateway API để route traffic north-south qua `Gateway` + `HTTPRoute`.
- Giữ nguyên nguyên tắc GitOps: **Argo CD là source of truth**; mọi manifest chính thức phải nằm trong Git.

> **Lưu ý quan trọng:** Có thể cài thử bằng CLI để kiểm tra nhanh, nhưng khi chốt production flow thì đưa cấu hình vào Git/ArgoCD để tránh drift.

#### 1.7.1. Cài Gateway API CRDs (một lần trên mỗi workload cluster)

```bash
for ctx in kind-dev kind-staging kind-prod; do
  kubectl --context "$ctx" apply -f \
    https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.1/standard-install.yaml
done
```

#### 1.7.2. Cài Cilium bằng Argo CD (GitOps chuẩn)

Từ cluster `kind-management`, apply 3 bootstrap Application:

```bash
kubectl config use-context kind-management
cd ~/Downloads/practice_RKE2

kubectl apply -f argocd/bootstrap/09-cilium-dev.yaml
kubectl apply -f argocd/bootstrap/10-cilium-staging.yaml
kubectl apply -f argocd/bootstrap/11-cilium-prod.yaml
```

Sau đó sync ứng dụng Cilium:

```bash
argocd app sync argocd/cilium-dev
argocd app sync argocd/cilium-staging
argocd app sync argocd/cilium-prod
```

> Nếu `prod` đang policy `Manual`, giữ nguyên: sync `cilium-prod` thủ công khi bạn muốn rollout.

#### 1.7.2b. MetalLB (GitOps) — LoadBalancer cho Gateway trên Kind

1. Đăng ký Helm repo (một lần): `argocd repo add https://metallb.github.io/metallb --type helm --name metallb`
2. Cập nhật AppProject (namespace `metallb-system`): `kubectl apply -f argocd/bootstrap/01-projects.yaml`
3. Apply + sync:

   ```bash
   kubectl --context kind-management apply -f argocd/bootstrap/15-metallb-dev.yaml
   kubectl --context kind-management apply -f argocd/bootstrap/16-metallb-staging.yaml
   kubectl --context kind-management apply -f argocd/bootstrap/17-metallb-prod.yaml
   argocd app sync argocd/metallb-prod
   ```

4. Pool IP nằm trong `config/metallb/pools/{dev,staging,prod}/pool.yaml` — **mỗi cluster một dải** (`172.18.255.10-19` dev, `20-29` staging, `30-39` prod). Nếu `docker network inspect kind` không phải `172.18.0.0/16`, sửa các file đó cho khớp subnet.

5. Sau khi MetalLB **Healthy**, Service Gateway Cilium (`kubectl -n meo-stationery get svc`) sẽ có **EXTERNAL-IP**. Gọi:

   ```bash
   curl -sS -H 'Host: dev.meo.local' http://<EXTERNAL-IP>/api/health
   ```

   (`/etc/hosts`: `127.0.0.1 dev.meo.local` chỉ đúng khi bạn dùng NodePort/localhost; với IP MetalLB trên mạng Docker, thường **curl thẳng tới EXTERNAL-IP** là đủ.)

Kiểm tra nhanh:

```bash
for ctx in kind-dev kind-staging kind-prod; do
  echo "=== $ctx ==="
  kubectl --context "$ctx" -n kube-system get pods -l k8s-app=cilium
  kubectl --context "$ctx" -n kube-system get cm cilium-config -o yaml | rg "enable-wireguard|encrypt-node|enable-l7-proxy|loadbalancer-algorithm"
  kubectl --context "$ctx" -n kube-system get servicemonitor | rg "cilium|hubble" || true
done
```

#### 1.7.3. (Tuỳ chọn) Cài Cilium CLI cho break-glass

```bash
CILIUM_CLI_VERSION=$(curl -s https://raw.githubusercontent.com/cilium/cilium-cli/main/stable.txt)
CLI_ARCH=amd64
curl -L --fail --remote-name-all \
  "https://github.com/cilium/cilium-cli/releases/download/${CILIUM_CLI_VERSION}/cilium-linux-${CLI_ARCH}.tar.gz"{,.sha256sum}
sha256sum --check "cilium-linux-${CLI_ARCH}.tar.gz.sha256sum"
sudo tar xzvfC cilium-linux-${CLI_ARCH}.tar.gz /usr/local/bin
rm cilium-linux-${CLI_ARCH}.tar.gz{,.sha256sum}
cilium version
```

#### 1.7.4. Chạy một lệnh cho cả 3 cluster (sau reboot)

`GatewayClass`, `Gateway`, `HTTPRoute` đã được quản lý trong Helm chart (`template/templates/*.yaml`) và sẽ được Argo CD sync từ Git.

Lệnh một dòng để apply bootstrap Cilium Apps:

```bash
bash -lc 'set -euo pipefail; kubectl --context kind-management apply -f argocd/bootstrap/09-cilium-dev.yaml; kubectl --context kind-management apply -f argocd/bootstrap/10-cilium-staging.yaml; kubectl --context kind-management apply -f argocd/bootstrap/11-cilium-prod.yaml; argocd app sync argocd/cilium-dev; argocd app sync argocd/cilium-staging; argocd app sync argocd/cilium-prod'
```

Sau khi chạy lệnh trên, sync lại app stack để Helm chart apply `GatewayClass`/`Gateway`/`HTTPRoute`.

Kiểm tra nhanh các tính năng Cilium đã bật:

```bash
for ctx in kind-dev kind-staging kind-prod; do
  echo "=== $ctx ==="
  kubectl --context "$ctx" -n kube-system get cm cilium-config -o yaml | rg "enable-wireguard|encrypt-node|enable-l7-proxy|loadbalancer-algorithm"
  kubectl --context "$ctx" -n kube-system get servicemonitor | rg "cilium|hubble" || true
done
```

**Hubble UI**

- **`kind-management`:** ClusterIP — mở bằng CLI hoặc port-forward **localhost:12000** (mặc định của `cilium hubble ui`).
- **dev / staging / prod:** `hubble-ui` kiểu **NodePort** cố định trong Git (`cilium/cilium-cluster-*.yaml`): **31201** (dev), **31202** (staging), **31203** (prod). Trên Kind (Linux), lấy IP node rồi mở trình duyệt:

```bash
DEV_IP=$(docker inspect dev-control-plane        --format '{{.NetworkSettings.Networks.kind.IPAddress}}')
STG_IP=$(docker inspect staging-control-plane   --format '{{.NetworkSettings.Networks.kind.IPAddress}}')
PRD_IP=$(docker inspect prod-control-plane      --format '{{.NetworkSettings.Networks.kind.IPAddress}}')
echo "dev:      http://${DEV_IP}:31201"
echo "staging:  http://${STG_IP}:31202"
echo "prod:     http://${PRD_IP}:31203"
```

```bash
# Management → http://localhost:12000
cilium hubble ui --context kind-management
# hoặc: kubectl --context kind-management -n kube-system port-forward svc/hubble-ui 12000:80
```

**CLI flow (tuỳ chọn):** `cilium` không có `hubble observe`. Cần binary **`hubble`**: [cilium/hubble#installation](https://github.com/cilium/hubble#installation). Relay: `cilium hubble port-forward --context kind-dev --port-forward 4245` rồi `hubble observe flows --server localhost:4245 -f` (staging/prod: đổi context; chạy song song thì đổi `--port-forward` local).

#### 1.7.5. Truy cập app **không** `kubectl port-forward`

- **Khuyến nghị:** MetalLB GitOps — xem **1.7.2b** (`argocd/bootstrap/15–17`, `config/metallb/`).
- **Tùy chọn:** NodePort + `extraPortMappings` trong `kind/*-kind-config.yaml` (phải `kind delete`/`create` lại cluster) + `kubectl patch` Service `cilium-gateway-*`; xem các bản ghi cũ trong git nếu cần.
- **Cloud / RKE2:** dùng LoadBalancer / Ingress có sẵn — không cần MetalLB trên Kind.

> Nếu `GatewayClass` bị `Accepted: Unknown` và message `Waiting for controller`, kiểm tra lại thứ tự: CRDs -> Argo sync Cilium -> rollout restart `cilium-operator`/`cilium` (nếu cần).

### 1.8. Gỡ rối thường gặp (đọc trước khi blame doc)

**Argo CD là source of truth (GitOps)**

- Argo CD (cluster `kind-management`) là bên nắm trạng thái mong muốn của `Application`, Helm values và manifest Gateway API.
- Không maintain song song hai nguồn (vừa Argo vừa apply tay lâu dài), vì dễ gây drift và khó debug.
- Có thể test nhanh bằng `kubectl apply`/`helm` ở `kind-dev`, nhưng sau khi xác nhận phải đưa ngay về Git rồi sync lại bằng Argo CD.
- Nếu đã lỡ cài Helm tay đè lên workload Argo đang quản lý: gỡ release tay (`helm uninstall ...`) rồi refresh/sync lại app trên Argo.

**Argo CD báo app `Progressing` dù `Synced` — `Gateway` / `HTTPRoute` vẫn Progressing**

- Argo CD có health check riêng cho Gateway API: thường cần điều kiện kiểu *Programmed=True* / parent *Accepted* mới đánh **Healthy**.
- Trên **Kind**, Cilium Gateway đôi khi **không** báo đủ điều kiện đó (không có LB cloud, listener chưa “programmed” theo nghĩa Argo) → **HTTPRoute** và **Gateway** treo **Progressing** lâu hoặc mãi, dù manifest đã **Synced** và **Rollout** đã **Healthy**.
- Đây **không** phải lỗi `ignoreDifferences` (cái đó chỉ giảm **OutOfSync** do `.status`). Muốn cây Argo xanh hẳn: nâng phiên bản Argo CD, hoặc tùy chỉnh health Lua trong ConfigMap `argocd-cm` (`resource.customizations.health.gateway.networking.k8s.io_*`), hoặc chấp nhận **Progressing** khi lab Kind miễn traffic test nội bộ ổn.

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

**Grafana không thấy (hoặc thiếu) metrics từ cluster dev/staging/prod**

- Xem **mục 1.6.1**: sau recreate Kind, URL `remote_write` trong Git thường **sai**. Chạy `./scripts/sync-monitoring-remote-write-url.sh`, commit/push, sync lại `monitoring-{dev,staging,prod}`. Kiểm `./scripts/sync-monitoring-remote-write-url.sh --check`.
- Thứ tự: `monitoring-management` (05) phải **Healthy** trước khi kỳ vọng agent push. Pod trên workload cluster **không** nhất thiết `curl` được tới IP management (mạng Kind tách cluster) — đừng dùng `kubectl run curl` trên dev để kết luận Prometheus management chết; test từ **host** hoặc `--check` như trên.

**ServiceAccount “exists and cannot be imported into the current release”**

- Tài nguyên đã được tạo trước đó không thuộc Helm release hiện tại. Trên môi trường practice: ưu tiên **một** luồng (Argo **hoặc** Helm tay); tránh vừa Argo vừa `helm upgrade` cùng release.

---

## 2. Kiểm tra nhanh

- Remote write (sau recreate Kind): `./scripts/sync-monitoring-remote-write-url.sh --check` — xem **1.6.1**.
- ClusterMesh: `bash scripts/kind-clustermesh-status.sh` (hoặc `cilium clustermesh status --context kind-management`).
- UI ArgoCD: https://localhost:8080 → Applications: `dev-*`, `monitoring-*`...
- UI Grafana (tập trung; series từ workload có nhãn `cluster` / `environment` từ remote_write):
  ```bash
  kubectl -n monitoring port-forward svc/monitoring-management-grafana 3000:80
  # Truy cập: http://localhost:3000 (admin / admin)
  ```
- Management: `kubectl --context kind-management get pods -n monitoring`
- Dev: `kubectl --context kind-dev get pods -n monitoring`
- Staging: `kubectl --context kind-staging get pods -A`
- Prod: `kubectl --context kind-prod get pods -A`

---

## 3. Lưu ý

- Replica count / image tag trong `env/<env>.yaml`. Chart workload `template/`; profile `app/be.yaml`, `app/db.yaml`; config `config/base/config.yaml`, override `config/env/<env>.yaml`.
- **Kind API / TLS:** `bash scripts/kind-fix-kubeconfig-servers.sh` sau `kind create`. Trên **management**, **trước** `helm install cilium` — nếu Helm lỗi TLS thì không có CNI (`disableDefaultCNI`) và Argo CD **Pending**.
- **Helm Cilium + ServiceMonitor:** Lần đầu trên management **chưa** có kube-prometheus-stack → dùng **hai** file values: `cilium-values-management.yaml` + `cilium-values-management-bootstrap.yaml` (mục **1.2**). Lỗi `no matches for kind "ServiceMonitor"` = thiếu bước này hoặc chưa cài CRD Prometheus Operator.
- **Hubble UI / CLI:** Management → port-forward **12000**. Workload → NodePort **31201 / 31202 / 31203** (IP `docker inspect *-control-plane`). CLI flow: `cilium hubble port-forward` + **`hubble observe flows`** — **mục 1.7.4**.
- **ClusterMesh (spoke):** IP hub trong `cilium/clustermesh-management-peer.yaml` — `bash scripts/kind-clustermesh-peer-ip.sh` sau mỗi lần recreate Kind (rồi push Git nếu Argo trỏ remote).
- **Monitoring remote_write:** Sau mỗi lần recreate Kind, chạy `./scripts/sync-monitoring-remote-write-url.sh` rồi commit/push và sync agent — chi tiết **1.6.1**. Management không còn scrape tĩnh node-exporter/kube-state từ các workload cluster; nếu bỏ bước này, Grafana thiếu series theo `cluster`/`environment`.
- **Linux:** Argo CD → API dev/staging/prod dùng **container IP + 6443** (mục **1.4**). `docker inspect <cluster>-control-plane --format '{{.NetworkSettings.Networks.kind.IPAddress}}'`. Không dùng `host.docker.internal` trên Linux.
- Đổi port trong `kind/*-kind-config.yaml` thì cập nhật tương ứng mục **1.4** và `scripts/kind-fix-kubeconfig-servers.sh` nếu cần.
- **RAM:** Nhiều cụm Kind song song dễ thiếu bộ nhớ → **kind/README.md**.
- **Database/backend:** ESO+AWS (**mục 1.5.1**) hoặc Secret tĩnh (**mục 1.5.2**). Lệnh có pipe: `--context` ở **cả hai** phía.
