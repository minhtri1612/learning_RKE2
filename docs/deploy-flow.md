# Flow deploy đầy đủ (provision + configure)

Thứ tự chạy script **không đổi**:

1. `provision.py management` → AWS infra + OpenVPN  
2. Bật VPN (vd. `sudo openvpn --config sep_tong.ovpn`)  
3. `configure.py management` → cài ArgoCD + apply bootstrap (root app, appsets, **argocd-apps**)  
4. `provision.py dev` → AWS infra dev  
5. `configure.py dev` → Rancher + ESO (dev)  
6. `provision.py prod` → AWS infra prod  
7. `configure.py prod` → Rancher + ESO (prod)  

## Cần thay đổi gì không?

**Script (`provision.py`, `configure.py`) không cần sửa.**

Chỉ cần: **push code mới lên repo mà ArgoCD đọc** (vd. `learning_RKE2`) **trước khi chạy bước 3** (hoặc trước khi ArgoCD sync lần đầu). Cụ thể:

- Repo phải có: `argocd/apps/definitions/*.yaml` (định nghĩa app generic: backend, database), `argocd/appsets/appset-applications.yaml` (ApplicationSet matrix: list env dev/prod × definitions). App (meo-station-backend-dev/prod, database-dev/prod) do ApplicationSet sinh, không còn folder argocd/apps/dev|prod với từng file.

Nếu chạy bước 3 khi repo chưa push code mới, ArgoCD sẽ sync theo state cũ. Sau khi push, Refresh/Sync lại root app (root-appsets) là được.
