# Kết nối kubectl tới Management cluster

Lỗi `dial tcp 127.0.0.1:6446: connection refused` nghĩa là kubeconfig **tunnel** (`.kube_config_rke2_management_tunnel.yaml`) đang trỏ tới `127.0.0.1:6446` nhưng **chưa có tunnel chạy** nên không kết nối được API server.

Bạn chọn **một trong hai cách** dưới đây.

---

## Cách 1: Dùng kubeconfig trực tiếp (qua VPN) – đơn giản nhất

1. **Bật VPN** vào mạng management (OpenVPN, file `.ovpn` từ `provision.py management`).
2. Dùng kubeconfig **không phải tunnel** (file do `provision.py` tạo, server = IP private management, port 6443):

```bash
export KUBECONFIG=$(pwd)/kube_config_rke2_management.yaml
kubectl get nodes
```

Nếu `get nodes` chạy được thì dùng luôn file này để tạo secret:

```bash
kubectl --kubeconfig=kube_config_rke2_management.yaml \
  create secret generic argocd-notifications-secret \
  -n argocd \
  --from-literal=slack-token=xoxb-... \
  --dry-run=client -o yaml | \
  kubectl --kubeconfig=kube_config_rke2_management.yaml apply -f -
```

**Lưu ý:** File `kube_config_rke2_management.yaml` chỉ tồn tại sau khi chạy `./provision.py management` (và có quyền đọc kubeconfig từ master). Nếu bạn chỉ có file tunnel thì dùng Cách 2.

---

## Cách 2: Chạy SSH tunnel rồi dùng kubeconfig tunnel

Kubeconfig `.kube_config_rke2_management_tunnel.yaml` trỏ tới `https://127.0.0.1:6446`. Cần có process forward **localhost:6446** → **management master:6443** qua SSH (jump host = OpenVPN).

### Bước 1: Lấy IP

- **OpenVPN (jump) IP:** từ Terraform hoặc `terraform/environments/management/management_state.json` → `openvpn_public_ip`.
- **Management master IP:** trong file `kube_config_rke2_management.yaml` (trường `server`, ví dụ `https://10.0.101.xx:6443`) hoặc từ Terraform output.

### Bước 2: Chạy tunnel (để chạy nền, giữ terminal mở hoặc dùng `screen`/`tmux`)

```bash
# Thay OPENVPN_IP và MANAGEMENT_MASTER_IP bằng giá trị thực
ssh -i terraform/environments/management/k8s-key.pem \
  -L 6446:MANAGEMENT_MASTER_IP:6443 \
  ubuntu@OPENVPN_IP \
  -N -o ServerAliveInterval=60
```

Ví dụ:

```bash
ssh -i terraform/environments/management/k8s-key.pem \
  -L 6446:10.0.101.50:6443 \
  ubuntu@3.xxx.xxx.xxx \
  -N -o ServerAliveInterval=60
```

Chạy lệnh này trong một terminal và **giữ cho nó chạy**. Terminal khác mới dùng kubectl.

### Bước 3: Dùng kubeconfig tunnel

```bash
kubectl --kubeconfig=.kube_config_rke2_management_tunnel.yaml get nodes
```

Nếu OK thì tạo secret:

```bash
kubectl --kubeconfig=.kube_config_rke2_management_tunnel.yaml \
  create secret generic argocd-notifications-secret \
  -n argocd \
  --from-literal=slack-token=xoxb-... \
  --dry-run=client -o yaml | \
  kubectl --kubeconfig=.kube_config_rke2_management_tunnel.yaml apply -f -
```

---

## Tóm tắt

| Tình huống | Cách làm |
|------------|----------|
| Đã bật VPN, có `kube_config_rke2_management.yaml` | Dùng Cách 1 (kubeconfig trực tiếp). |
| Chỉ có file tunnel, không VPN hoặc muốn qua tunnel | Chạy SSH tunnel (Cách 2) rồi dùng `.kube_config_rke2_management_tunnel.yaml`. |

Lỗi `connection refused` trên 127.0.0.1:6446 = **chưa chạy tunnel** (Cách 2) hoặc đang dùng nhầm file tunnel trong khi không có tunnel (nên chuyển sang Cách 1 nếu đã bật VPN).
