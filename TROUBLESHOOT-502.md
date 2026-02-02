# 502 Bad Gateway – Rancher / ArgoCD

## Tại sao 502?

Luồng request: **Browser → ALB (80/443) → Node (RKE2 Ingress 80/443) → Ingress route theo Host → Service Rancher/ArgoCD → Pod**.

- **Ingress (RKE2 có sẵn)** nhận request, xem Host = rancher.local / argocd.local, forward tới **backend** (Rancher service / ArgoCD server).
- **502** = Ingress gọi được backend nhưng **backend không trả về response hợp lệ** (timeout, connection refused, lỗi upstream).

**Nguyên nhân thường gặp:**

1. **Pod Rancher/ArgoCD chưa Ready** – Rancher lần đầu mất **5–10 phút** (pull image, bootstrap). ArgoCD vài phút. Vào quá sớm → backend chưa listen → 502.
2. **Pod crash / ImagePullBackOff** – Pod không chạy → service không có endpoint → Ingress gọi không được → 502.
3. **Backend port sai** – Ít gặp nếu dùng Helm chart đúng.

**meo-stationery.local** load được vì backend (meo-stationery) đã Ready. **rancher.local / argocd.local** 502 = pod Rancher/ArgoCD chưa sẵn sàng hoặc lỗi. EC2 chạy không liên quan – 502 xảy ra ở tầng Kubernetes (pods/services).

---

## Website chạy nhưng VPN/SSH fail?

- **Website (meo-stationery.local, rancher.local)** đi qua **ALB (public)** → không cần VPN.
- **VPN / SSH vào 10.0.x.x** cần tunnel: client kết nối OpenVPN server → mới vào được private subnet. Nếu VPN log báo **TLS handshake failed** hoặc **link remote: 3.x.x.x** khác với `terraform output openvpn_public_ip` → file **minhtri.ovpn** đang trỏ **IP cũ** (server đã recreate). Chạy `./scripts/refresh-ovpn.sh` rồi `sudo systemctl restart openvpn-practice-rke2`.

---

## Cần làm gì?

### 1. Cho `kubectl` chạy được (đang bị TLS handshake timeout)

Kubeconfig trỏ `https://127.0.0.1:6443` → cần **VPN thực sự kết nối** và **port-forward** đang chạy.

**Nếu VPN service chạy nhưng log có "TLS handshake failed" / "Restart pause 300s"** → tunnel chưa lên (process retry liên tục). Làm lần lượt:

1. **Sửa VPN cho đúng IP server:**  
   `minhtri.ovpn` phải trùng `terraform output openvpn_public_ip`. Nếu khác (ví dụ destroy/apply lại) → **cập nhật .ovpn rồi restart VPN**:
   ```bash
   ./scripts/refresh-ovpn.sh
   sudo systemctl restart openvpn-practice-rke2
   journalctl -u openvpn-practice-rke2 -f
   ```
   Đợi thấy **"Initialization Sequence Completed"**. Nếu vẫn lỗi → chạy `./debug-vpn.sh` và so IP trong .ovpn vs terraform output.

2. **Sau khi VPN đã lên**, bật **port-forward** (1 terminal, để chạy nền). Nếu báo **"Address already in use" / "cannot listen to port: 6443"** thì port đã bị process cũ (SSH tunnel từ lần deploy trước) chiếm — dùng luôn (thử `kubectl get nodes`) hoặc giải phóng rồi chạy lại:
   ```bash
   pkill -f 'ssh.*-L 6443:.*6443'   # kill tunnel cũ
   sleep 2
   # rồi chạy lệnh ssh -N -L ... bên dưới
   ```
   **Lưu ý:** Lệnh `ssh -N -L ...` khi chạy thành công **sẽ không in gì** — nó chỉ giữ tunnel. Để nguyên terminal đó, mở terminal **khác** để chạy `kubectl`.

   **Nếu `kubectl get nodes` báo "connection to 127.0.0.1:6443 refused"** = tunnel không chạy. Kiểm tra: `ss -tlnp | grep 6443` (trống = không có tunnel). Cần **2 terminal**: (1) chạy lệnh `ssh -N -L ...` bên dưới và **không tắt, không Ctrl+C**; (2) chạy `kubectl`. Nếu lệnh ssh thoát ngay (về prompt) = kết nối lỗi (VPN chưa lên? SSH fail?) — kiểm tra VPN: `ping 10.0.101.125` (trong VPC), hoặc `systemctl status openvpn-practice-rke2`.

```bash
cd /home/minhtri/Downloads/practice_RKE2
OPENVPN_IP=$(cd terraform && terraform output -raw openvpn_public_ip)
MASTER_IP=$(cd terraform && terraform output -json master_private_ip | python3 -c "import sys,json; print(json.load(sys.stdin)[0])")
ssh -N -L 6443:${MASTER_IP}:6443 -i terraform/k8s-key.pem -o StrictHostKeyChecking=no -o ProxyCommand="ssh -i terraform/k8s-key.pem -o StrictHostKeyChecking=no -W %h:%p ubuntu@${OPENVPN_IP}" ubuntu@${MASTER_IP}
```
(Để terminal này chạy; không tắt. Nếu thấy prompt lại ngay = ssh lỗi.)

Terminal khác:

```bash
export KUBECONFIG=/home/minhtri/Downloads/practice_RKE2/kube_config_rke2.yaml
kubectl get nodes
```

### 2. Kiểm tra pods Rancher / ArgoCD

```bash
kubectl get pods -n cattle-system    # Rancher
kubectl get pods -n argocd          # ArgoCD
kubectl get ingress -A               # Ingress cho rancher.local / argocd.local
```

- Nếu pod **Not Ready** hoặc **CrashLoopBackOff** → xem log: `kubectl logs -n cattle-system -l app=rancher` (tương tự cho argocd).

**ArgoCD repo-server crashloop (0/1 Running, nhiều restarts):** Log có `Error serving health check request ... context canceled` rồi `got signal terminated, attempting graceful shutdown` → probe (liveness/readiness) timeout quá ngắn, K8s kill pod. Đã xử lý trong `argocd/values-nodeselector.yaml` bằng cách tăng `repoServer.readinessProbe` / `repoServer.livenessProbe` (initialDelaySeconds, timeoutSeconds, failureThreshold). Sau khi sửa values, upgrade ArgoCD **chạy trên máy local** (không cần SSH vào master), dùng đúng kubeconfig trong repo và có VPN (hoặc SSH tunnel):

```bash
cd /home/minhtri/Downloads/practice_RKE2
export KUBECONFIG=/home/minhtri/Downloads/practice_RKE2/kube_config_rke2.yaml
helm upgrade argocd argo/argo-cd -n argocd -f argocd/values-nodeselector.yaml
```

Nếu báo **"no such host"** hoặc **"cluster unreachable"** với hostname NLB → đang dùng kubeconfig khác (ví dụ `~/.kube/config`) trỏ NLB; set `KUBECONFIG` như trên (file trong repo trỏ **master private IP**). Cần **VPN đã kết nối** để tới được master; nếu dùng SSH tunnel thì dùng file `.kube_config_rke2_tunnel.yaml` và giữ tunnel đang chạy.

Nếu báo **pre-upgrade hooks failed: redis-secret-init ... Timeout / context deadline exceeded** → hook Job chạy lâu hơn mặc định (5m). Chạy lại với timeout lớn hơn:
```bash
helm upgrade argocd argo/argo-cd -n argocd -f argocd/values-nodeselector.yaml --timeout 10m
```
Nếu Job hook đang treo, xóa rồi upgrade lại: `kubectl delete job -n argocd -l app.kubernetes.io/name=argocd` (chỉ job redis-secret-init), rồi chạy lệnh helm trên.

### 3. RKE2 đã có sẵn Nginx Ingress

RKE2 cài sẵn **Nginx Ingress Controller** (DaemonSet, hostNetwork, port 80/443). Không cần cài thêm. 502 = backend (Rancher/ArgoCD) chưa trả lời, không phải thiếu Ingress.

### 4. Rancher / ArgoCD lâu mới sẵn sàng

- Rancher lần đầu có thể mất **5–10 phút** (pull image, khởi tạo).
- ArgoCD cũng cần vài phút. Kiểm tra: `kubectl get pods -n cattle-system -w` và `kubectl get pods -n argocd -w`.

---

**Tóm tắt:** 502 = backend (Rancher/ArgoCD) chưa trả lời Ingress. RKE2 đã có sẵn Nginx Ingress (80/443). Cần (1) VPN + port-forward để chạy `kubectl`, (2) kiểm tra pods Rancher/ArgoCD và ingress.

---

## 503 Service Unavailable (Rancher)

Pod Rancher **1/1 Running** nhưng browser báo **503** = Rancher process trong pod chưa sẵn sàng nhận request (bootstrap) hoặc lỗi nội bộ.

- **Thử:** https://localhost:8443 (port-forward backup, nếu đang chạy).
- **Đợi 2–5 phút** rồi reload https://rancher.local/dashboard/
- **Xem log:** `kubectl logs -n cattle-system -l app=rancher --tail=80`

---

## meo-stationery: trang load nhưng "Không tìm thấy sản phẩm"

Frontend chạy; vấn đề là **dữ liệu** (backend hoặc DB). Pods 1/1 nhưng DB có thể trống hoặc backend không kết nối DB.

Trên master (SSH vào 10.0.101.125):

```bash
# Log backend (lỗi kết nối DB?)
kubectl logs -n meo-stationery -l app=meo-station-backend --tail=50

# DB có bảng và có dữ liệu không?
kubectl exec -n database postgres-0 -- psql -U meo_admin -d meo_stationery -c '\dt'
kubectl exec -n database postgres-0 -- psql -U meo_admin -d meo_stationery -c 'SELECT COUNT(*) FROM "Product";'
```

- Nếu **COUNT = 0** hoặc **relation "Product" does not exist**: DB chưa có schema → **migration chưa chạy hoặc đã fail**.

**Nếu DB không có bảng (Did not find any relations):**

1. **Kiểm tra job migration** (trên master, SSH vào 10.0.101.125):
   ```bash
   kubectl get jobs -n meo-stationery
   kubectl get pods -n meo-stationery | grep migration
   ```
   Nếu có pod migration **Failed** hoặc **Error** → xem log: `kubectl logs -n meo-stationery <migration-pod-name>`.

2. **Chạy migration** – Job `prisma migrate deploy` + seed nằm trong `k8s_helm/backend/templates/migration-job.yaml`. ArgoCD sync **không** chạy Helm hook nên job có thể không được tạo. Chạy thủ công từ chart:
   - **Chạy trên máy local** (có repo, helm, kubectl). Phải dùng **KUBECONFIG trỏ 127.0.0.1:6443** và **port-forward đang chạy** (VPN + SSH tunnel). Nếu kubectl báo `no such host` với hostname NLB thì đang dùng kubeconfig sai — dùng file trong repo:
   ```bash
   # Terminal 1: bật tunnel (VPN đã kết nối), để chạy nền
   cd /home/minhtri/Downloads/practice_RKE2
   OPENVPN_IP=$(cd terraform && terraform output -raw openvpn_public_ip)
   MASTER_IP=$(cd terraform && terraform output -json master_private_ip | python3 -c "import sys,json; print(json.load(sys.stdin)[0])")
   ssh -N -L 6443:${MASTER_IP}:6443 -i terraform/k8s-key.pem -o StrictHostKeyChecking=no -o ProxyCommand="ssh -i terraform/k8s-key.pem -o StrictHostKeyChecking=no -W %h:%p ubuntu@${OPENVPN_IP}" ubuntu@${MASTER_IP}

   # Terminal 2: từ repo root
   export KUBECONFIG=/home/minhtri/Downloads/practice_RKE2/kube_config_rke2.yaml
   kubectl get nodes   # kiểm tra đã thấy cluster
   helm template meo-station-backend k8s_helm/backend -n meo-stationery -f k8s_helm/backend/values.yaml --show-only templates/migration-job.yaml | kubectl apply -n meo-stationery -f -
   kubectl wait -n meo-stationery --for=condition=complete job/meo-station-backend-migration --timeout=600s
   ```
   (Nếu job cũ còn Failed: `kubectl delete job -n meo-stationery meo-station-backend-migration` rồi chạy lại lệnh `helm template ... | kubectl apply`.)

3. **Log backend** (label đúng là `app.kubernetes.io/name=backend-deployment`):
   ```bash
   kubectl logs -n meo-stationery -l app.kubernetes.io/name=backend-deployment --tail=50
   # hoặc theo tên pod:
   kubectl logs -n meo-stationery meo-station-backend-f74dc68fd-5t645 --tail=50
   ```

- Nếu **backend log** có lỗi kết nối DB: kiểm tra `DATABASE_URL`, service `postgres.database`, network policy.
