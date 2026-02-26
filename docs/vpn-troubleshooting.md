# OpenVPN – Xử lý lỗi không kết nối được

## Triệu chứng

- **UDPv4 link remote: [AF_INET]3.104.152.55:1194** (IP cũ) → TLS key negotiation failed.
- Hoặc **IP đã đúng (13.237.128.122)** nhưng vẫn **TLS handshake failed** (timeout 60s).

## Nguyên nhân thường gặp

1. **File .ovpn trỏ IP cũ** (server đã recreate / EIP đổi).
2. **Cert trong .ovpn không khớp server** (server mới, CA/cert mới; .ovpn vẫn dùng cert cũ).
3. **Mạng chặn UDP 1194** → thử kết nối qua TCP 443.

## Cách xử lý

### Bước 1: Cập nhật IP trong .ovpn (chỉ đổi dòng `remote`)

Khi chỉ **đổi IP** (terraform state có IP mới, server không recreate):

```bash
./scripts/update-ovpn-remote.sh
```

Sau đó:

```bash
sudo openvpn --config sep_tong.ovpn
```

### Bước 2: Tạo lại .ovpn từ server (đúng cert + IP)

Khi **vẫn lỗi TLS** sau bước 1 (thường do server đã recreate, CA/cert mới):

```bash
./scripts/refresh-ovpn.sh
```

Script sẽ SSH lên OpenVPN server, chạy Ansible, tạo lại file .ovpn và tải về. Cần:

- SSH được tới IP OpenVPN (trong SG cho phép SSH từ IP của bạn).
- Key: `terraform/environments/management/k8s-key.pem`.

Sau khi xong:

```bash
sudo openvpn --config sep_tong.ovpn
```

### Bước 3: Thử TCP nếu UDP bị chặn

Nếu **UDP 1194** bị chặn (ISP/công ty), dùng bản **TCP 443**:

1. Mở TCP 443 trên AWS (nếu chưa):
   ```bash
   cd terraform/environments/management && terraform apply
   ```
2. Chạy lại refresh để có file `*-tcp.ovpn`:
   ```bash
   ./scripts/refresh-ovpn.sh
   ```
3. Kết nối bằng TCP:
   ```bash
   sudo openvpn --config sep_tong-tcp.ovpn
   ```

## Tóm tắt

| Tình huống | Lệnh |
|------------|------|
| Chỉ đổi IP (EIP/server mới, cert giữ nguyên) | `./scripts/update-ovpn-remote.sh` rồi `sudo openvpn --config sep_tong.ovpn` |
| Lỗi TLS (server recreate, cert mới) | `./scripts/refresh-ovpn.sh` rồi `sudo openvpn --config sep_tong.ovpn` |
| UDP bị chặn | Mở TCP 443 (terraform apply), `./scripts/refresh-ovpn.sh`, rồi `sudo openvpn --config sep_tong-tcp.ovpn` |
