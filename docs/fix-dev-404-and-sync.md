# Sửa 404 meo-stationery-dev/prod + ArgoCD "revision main must be resolved"

**Fix nhanh (một script):** Đã bật VPN thì chạy:
```bash
./scripts/fix-argocd-and-404-full.sh
```
Script sẽ: kiểm tra YAML cluster, nhắc push đúng repo ArgoCD đang dùng, apply cluster secrets, xóa webhook dev+prod, refresh ArgoCD apps.

---

**Đã tự động hóa trong flow:** Khi chạy đúng thứ tự (provision → VPN → configure management → provision dev → configure dev → provision prod → configure prod), IP lấy từ kubeconfig, webhook xóa tự động. Nếu vẫn 404 hoặc ArgoCD báo lỗi, làm tay theo dưới đây.

---

## 1. Cập nhật IP cluster dev (ArgoCD trỏ đúng cluster)

**Vì sao:** Secret `cluster-dev` trên management đang lưu IP cũ (ví dụ .42). Master dev mới có IP khác (ví dụ .25). ArgoCD gọi nhầm IP → timeout → không deploy được app xuống dev.

**Cách làm (chọn 1 trong 2):**

### Cách A – Script (VPN bật, có kubeconfig management)

```bash
export KUBECONFIG=$(pwd)/kube_config_rke2_management.yaml
bash scripts/create-argocd-cluster-secrets.sh dev
```

Script đọc `kube_config_rke2_dev.yaml` (IP mới), apply secret lên management và cập nhật file `argocd/clusters/cluster-dev.yaml`. Có thể `git add argocd/clusters && git commit -m "chore: cluster dev IP" && git push` để Git đồng bộ.

### Cách B – Chỉ cập nhật file (không cần VPN tới management)

```bash
./scripts/update-argocd-cluster-manifest-from-kubeconfig.sh dev
git add argocd/clusters/cluster-dev.yaml && git commit -m "fix: cluster dev IP" && git push
export KUBECONFIG=$(pwd)/kube_config_rke2_management.yaml
kubectl delete secret cluster-dev -n argocd
```

ArgoCD app `argocd-clusters` sẽ sync và tạo lại secret từ Git với IP mới.

---

## 2. Xóa webhook ingress-nginx (để Ingress apply được)

**Vì sao:** Khi ArgoCD apply Ingress, API server gọi webhook `validate.nginx.ingress.kubernetes.io`. Cert webhook tự ký → API server không tin → **x509: certificate signed by unknown authority** → Ingress bị từ chối → Missing → 404.

**Cách làm (VPN bật, KUBECONFIG=dev):**

```bash
export KUBECONFIG=$(pwd)/kube_config_rke2_dev.yaml
kubectl delete validatingwebhookconfiguration dev-ingress-nginx-admission
```

Hoặc chạy script:

```bash
./scripts/fix-ingress-nginx-webhook-dev.sh
```

(Script tự tìm webhook có tên chứa `ingress`/`nginx` và xóa; nếu có nhiều cái, có thể cần xóa đúng tên `dev-ingress-nginx-admission`.)

Sau đó vào ArgoCD bấm **Sync** lại **meo-station-backend-dev**. Ingress sẽ apply được → **meo-stationery-dev.local** hết 404.

---

## "Unable to load data: revision main must be resolved"

ArgoCD không fetch được branch **main** từ repo Git. Thường do:

| Nguyên nhân | Cách xử lý |
|-------------|------------|
| Repo **private** (GitHub) | Thêm credentials: sửa `argocd/repositories/repo-credentials.yaml` (username + password/token), apply lên management. Hoặc ArgoCD UI → Settings → Repositories → thêm repo với token. |
| Repo/branch sai | ArgoCD đang trỏ `learning_RKE2` branch `main`. Nếu bạn push từ repo khác (vd. practice_RKE2), phải push `argocd/` lên đúng repo đó, hoặc đổi `repoURL` / `targetRevision` trong `argocd/bootstrap/02-root-app.yaml` và appsets. |
| File trong repo **lỗi YAML** | Ví dụ `argocd/clusters/cluster-prod.yaml` từng bị lỗi (dòng thừa). Đã fix local thì push lại: `git add argocd/clusters && git commit -m "fix: cluster yaml" && git push`. Sau đó ArgoCD → app → Hard Refresh. |

Sau khi push đúng repo + branch, vào ArgoCD UI → từng app lỗi → **REFRESH** (Hard) rồi **SYNC**.

---

## Tóm tắt thứ tự (làm tay)

| Bước | Lệnh / Việc làm |
|------|------------------|
| 1 | Cập nhật IP: `bash scripts/create-argocd-cluster-secrets.sh dev` (KUBECONFIG=management) **hoặc** update manifest + push + xóa secret `cluster-dev` trên management |
| 2 | Xóa webhook: `kubectl delete validatingwebhookconfiguration dev-ingress-nginx-admission` (KUBECONFIG=dev) |
| 3 | ArgoCD: Sync lại **meo-station-backend-dev** (và **meo-station-database-dev** nếu cần) |

**Tự động trong script:**
- **provision.py dev/prod:** Cập nhật `argocd/clusters/cluster-<env>.yaml` từ kubeconfig (IP mới) và gọi `create-argocd-cluster-secrets.sh` để apply secret lên management (nếu có management kubeconfig).
- **configure.py dev/prod:** Gọi `fix-ingress-nginx-webhook.sh` cho env hiện tại; **configure.py prod** còn xóa webhook trên dev và (nếu có argocd CLI) trigger sync `meo-station-backend-dev` / `meo-station-backend-prod`.
- Không hardcode IP — mỗi lần terraform destroy rồi chạy lại flow đầy đủ thì IP được cập nhật từ kubeconfig.
