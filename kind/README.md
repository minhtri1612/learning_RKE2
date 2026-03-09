# Kind – 3 cluster (management + dev + prod)

Giống kiến trúc cloud: **1 cluster management** (chạy Argo CD) quản lý **1 dev** và **1 prod**.

| File | Mô tả |
|------|--------|
| `management-kind-config.yaml` | Kind config cho cluster **management** (Argo CD), API port **33443** |
| `dev-kind-config.yaml` | Kind config cho cluster **dev**, API port **30443** |
| `prod-kind-config.yaml` | Kind config cho cluster **prod**, API port **31443** |
| `dev-argocd-manager.yaml` | ServiceAccount + RBAC trên cluster **dev** (token cho Argo CD gọi API dev) |
| `prod-argocd-manager.yaml` | ServiceAccount + RBAC trên cluster **prod** (token cho Argo CD gọi API prod) |
| **KIND-THREE-CLUSTERS.md** | **Hướng dẫn từng bước**: tạo 3 cluster → cài Argo CD trên management → đăng ký dev + prod → apply bootstrap |

---

## Chạy theo thứ tự (từ thư mục gốc repo)

### Bước 1: Tạo 3 cluster (3 file `*-kind-config.yaml`)

```bash
kind create cluster --name management --config kind/management-kind-config.yaml
kind create cluster --name dev --config kind/dev-kind-config.yaml
kind create cluster --name prod --config kind/prod-kind-config.yaml
kubectl config get-contexts   # kiểm tra kind-management, kind-dev, kind-prod
```

### Bước 2: Cài Argo CD trên cluster management

```bash
kubectl config use-context kind-management
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd wait --for=condition=Ready pods --all --timeout=300s
# Lấy password: kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d && echo
# Port-forward UI (giữ terminal): kubectl -n argocd port-forward svc/argocd-server 8080:443
```

### Bước 3: Apply 2 file argocd-manager (SA + token trên dev và prod)

```bash
kubectl --context kind-dev apply -f kind/dev-argocd-manager.yaml
kubectl --context kind-prod apply -f kind/prod-argocd-manager.yaml
sleep 5
```

### Bước 4: Đăng ký cluster dev + prod với Argo CD

Lấy token:

```bash
DEV_TOKEN=$(kubectl --context kind-dev get secret argocd-manager-long-lived-token -n kube-system -o jsonpath='{.data.token}' | base64 -d)
PROD_TOKEN=$(kubectl --context kind-prod get secret argocd-manager-long-lived-token -n kube-system -o jsonpath='{.data.token}' | base64 -d)
```

Tạo secret (Mac/Windows: `host.docker.internal`, Linux Kind: **`172.18.0.1`** — Kind network gateway; dùng 172.17.0.1 sẽ bị i/o timeout):

```bash
kubectl config use-context kind-management
kubectl create secret generic cluster-dev -n argocd \
  --from-literal=name=dev \
  --from-literal=server=https://host.docker.internal:30443 \
  --from-literal=config="{\"bearerToken\":\"$DEV_TOKEN\",\"tlsClientConfig\":{\"insecure\":true}}"
kubectl label secret cluster-dev -n argocd argocd.argoproj.io/secret-type=cluster

kubectl create secret generic cluster-prod -n argocd \
  --from-literal=name=prod \
  --from-literal=server=https://host.docker.internal:31443 \
  --from-literal=config="{\"bearerToken\":\"$PROD_TOKEN\",\"tlsClientConfig\":{\"insecure\":true}}"
kubectl label secret cluster-prod -n argocd argocd.argoproj.io/secret-type=cluster
```

### Bước 5: Add repo + apply bootstrap

```bash
kubectl config use-context kind-management
argocd login localhost:8080 --insecure --username admin --password "<password_bước_2>"
argocd repo add https://github.com/minhtri1612/learning_RKE2.git
kubectl apply -f argocd/projects/
kubectl apply -f argocd/repositories/
kubectl apply -f argocd/bootstrap/02-root-app.yaml
```

Xong. Mở https://localhost:8080 (khi đang port-forward) xem app sync.

---

## 5 file YAML dùng ở bước nào

| File | Bước | Lệnh |
|------|------|------|
| `management-kind-config.yaml` | 1 | `kind create cluster --name management --config kind/management-kind-config.yaml` |
| `dev-kind-config.yaml` | 1 | `kind create cluster --name dev --config kind/dev-kind-config.yaml` |
| `prod-kind-config.yaml` | 1 | `kind create cluster --name prod --config kind/prod-kind-config.yaml` |
| `dev-argocd-manager.yaml` | 3 | `kubectl --context kind-dev apply -f kind/dev-argocd-manager.yaml` |
| `prod-argocd-manager.yaml` | 3 | `kubectl --context kind-prod apply -f kind/prod-argocd-manager.yaml` |

---

Làm theo **KIND-THREE-CLUSTERS.md** nếu cần giải thích chi tiết từng bước.

`KIND-TWO-CLUSTERS.md` là bản cũ (2 cluster, Argo CD trên prod); dùng **KIND-THREE-CLUSTERS.md** cho setup chuẩn.

---

## Lỗi "could not find a log line that matches ... cgroup v1"

Gặp khi host dùng **cgroup v2** (Ubuntu 22.04+, Docker 24+). Binary Kind **v0.20** chỉ chờ log `detected cgroup v1`; trên cgroup v2 node in `detected cgroup v2` nên không khớp → phải dùng **Kind bản mới** (v0.24+ đã sửa).

**Cách 1 – Nâng cấp Kind lên v0.24+ (khuyến nghị)**

Tải vào file tạm (tránh ghi đè thư mục tên `kind`), rồi thay binary cũ:

```bash
# Linux amd64 – dùng /tmp để tránh conflict với thư mục kind trong repo
curl -Lo /tmp/kind-bin https://kind.sigs.k8s.io/dl/v0.24.0/kind-linux-amd64
chmod +x /tmp/kind-bin
sudo mv /tmp/kind-bin /usr/local/bin/kind
kind version
```

Sau đó tạo lại cluster:

```bash
kind create cluster --name management --config kind/management-kind-config.yaml
```

Bản mới hơn (vd. v0.31.0): đổi URL thành `https://kind.sigs.k8s.io/dl/v0.31.0/kind-linux-amd64`.

**Cách 2 – Cài qua package manager (nếu có)**

- Ubuntu/Debian: `sudo apt install kind` (có thể ra bản mới hơn v0.20).
- Hoặc: https://kind.sigs.k8s.io/docs/user/quick-start/#installation

Config trong repo đã có `containerdConfigPatches` + `image: kindest/node:v1.28.0`; sau khi nâng Kind xong thì không cần sửa thêm.

**Nếu vẫn lỗi sau khi nâng Kind (v0.24 / v0.31)**

Một số máy (Docker + kernel + cgroup v2) vẫn không in đúng log mà Kind chờ. Workaround: **tắt cgroup v2 trên host** để Docker và node chạy cgroup v1.

1. Sửa GRUB rồi reboot:
   ```bash
   sudo nano /etc/default/grub
   # Thêm vào GRUB_CMDLINE_LINUX: systemd.unified_cgroup_hierarchy=0
   # Ví dụ: GRUB_CMDLINE_LINUX="systemd.unified_cgroup_hierarchy=0"
   sudo update-grub
   sudo reboot
   ```
2. Sau khi vào lại: `docker info | grep -i cgroup` → nên thấy `Cgroup Version: 1`. Chạy lại `kind create cluster ...`.

**Lưu ý:** Tắt cgroup v2 là thay đổi toàn hệ thống. Cách khác: dùng **minikube** (3 profile: management, dev, prod) thay Kind.

---

## Lỗi kubelet isn't running / connection refused :10248 (cluster thứ 3)

**Cluster được tạo khi đã có 2 cluster chạy** (dù là dev hay prod) thường fail: kubelet trong container không start. Nguyên nhân thường **không phải thiếu RAM** mà là **giới hạn inotify** của Linux (kernel giới hạn số "file watcher" → kubelet cần rất nhiều → vượt limit → kubelet không chạy → connection refused :10248). Kind ghi nhận: [known-issues – too many open files](https://kind.sigs.k8s.io/docs/user/known-issues/#pod-errors-due-to-too-many-open-files).

**Cách sửa (chạy trên host Linux, có sudo):**

```bash
echo fs.inotify.max_user_watches=655360 | sudo tee -a /etc/sysctl.conf
echo fs.inotify.max_user_instances=1280 | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

Sau đó tạo lại cluster thứ 3 (vd. `kind create cluster --name prod --config kind/prod-kind-config.yaml`). Nếu vẫn fail, thử tăng thêm: `max_user_watches=1048576`, `max_user_instances=2048` rồi `sudo sysctl -p`.

**Script nhanh:** `bash kind/fix-inotify-for-3-clusters.sh` (chạy 1 lần trên host, cần sudo).

**Cách dùng ổn định:**

- **Chỉ chạy 2 cluster:** management + **dev** **hoặc** management + **prod**. Ví dụ chỉ cần dev:
  ```bash
  kind create cluster --name management --config kind/management-kind-config.yaml
  kind create cluster --name dev --config kind/dev-kind-config.yaml
  ```
  Khi cần test “prod” locally có thể trỏ app prod sang cluster dev tạm.

- **Muốn đủ 3 cluster:** tăng RAM cho Docker (vd. 8GB+), rồi tạo lần lượt management → dev → prod. Nếu vẫn fail cluster thứ 3 thì máy không đủ tài nguyên.

**Cách tăng RAM cho Docker (để chạy 3 cluster):**

- **Docker Desktop (Windows / Mac / Linux):** Mở Docker Desktop → **Settings** (hoặc **Preferences**) → **Resources** → **Memory**: đặt **8 GB** trở lên (khuyến nghị 10–12 GB nếu máy đủ). **Apply & Restart**. Sau đó tạo lại 3 cluster:
  ```bash
  kind create cluster --name management --config kind/management-kind-config.yaml
  kind create cluster --name dev --config kind/dev-kind-config.yaml
  kind create cluster --name prod --config kind/prod-kind-config.yaml
  ```
- **Linux dùng Docker Engine** (không dùng Docker Desktop): Docker dùng RAM của máy, không giới hạn riêng. Cần đảm bảo máy có **≥ 8 GB RAM** và đóng bớt ứng dụng khác trước khi tạo cluster thứ 3. Kiểm tra: `free -h`.

**Lỗi TLS `x509: certificate is valid for ..., not 0.0.0.0`:** kubeconfig đang trỏ server `https://0.0.0.0:<port>`, trong khi certificate API server không có 0.0.0.0. Sửa bằng cách đổi server sang `127.0.0.1`:
  ```bash
  kubectl config set-cluster kind-management --server=https://127.0.0.1:33443
  kubectl config set-cluster kind-dev --server=https://127.0.0.1:30443
  kubectl config set-cluster kind-prod --server=https://127.0.0.1:31443
  ```

**Lỗi `node(s) already exist for a cluster with the name "prod"`:** cluster đó đã tồn tại — không chạy lại `kind create cluster --name prod`. Kiểm tra bằng `kind get clusters`. Nếu đã có management + prod và chạy tiếp `kind create cluster --name dev` thì dev là cluster thứ 3 → dễ fail kubelet do RAM; nên chỉ giữ 2 cluster (management + dev hoặc management + prod).
