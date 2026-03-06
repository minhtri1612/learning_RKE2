# Luồng hoạt động GitOps với ArgoCD (GitOps Flow)

Tài liệu này mô tả chi tiết luồng sự kiện xảy ra từ lúc Lập trình viên (Developer) hoặc hệ thống CI thực hiện lệnh `git push` cho đến khi ứng dụng được tự động cập nhật trên Kubernetes Cluster thông qua ArgoCD.

## 🌟 Tổng quan kiến trúc
Dự án được xây dựng theo mô hình **App of Apps** với **ApplicationSet** để tự động hoá việc triển khai:
- **Nguồn chân lý duy nhất (Single Source of Truth):** Kho chứa Git (`minhtri1612/learning_RKE2`).
- **Bộ não điều phối (Control Plane):** ArgoCD (chạy trên cụm Management).
- **Môi trường đích (Target Clusters):** Cụm `dev` (`10.1.101.87`) và Cụm `prod` (`10.2.101.213`).

---

## 🔄 Chi tiết quy trình 6 bước khi Git Push

### Bước 1: Developer thay đổi cấu hình hoặc mã nguồn
Lập trình viên sửa đổi các file trong dự án, ví dụ:
- Nâng cấp cấu hình Helm Chart, sửa biến môi trường trong file `k8s_helm/backend/values-dev.yaml`.
- Thêm một ứng dụng mới vào hệ thống.
- Chạy lệnh: `git commit -m "Update backend config"` và `git push origin dev` (hoặc `main`).

### Bước 2: Github tiếp nhận thay đổi
Kho chứa mã nguồn trên Github tiếp nhận nhánh cập nhật mới nhất. Khác với mô hình CI/CD truyền thống (Push-based), ở phần này Github/Gitlab hành xử hoàn toàn thụ động. Không có kịch bản (script) hay đường ống (pipeline) nào từ Github đâm trực tiếp lệnh `kubectl apply` vào cụm Kubernetes. Mọi thứ được lưu trữ an toàn như một cuốn sổ cái.

### Bước 3: ArgoCD phát hiện thay đổi (Reconciliation Loop)
- Máy chủ ArgoCD đang chạy ở chế độ vòng lặp theo dõi liên tục định kỳ (trung bình 3 phút/lần). Dữ liệu kho được lưu trữ bởi file `repo-credentials.yaml`.
- Cỗ máy siêu tốc `appset-applications.yaml` (hoạt động dựa trên Git Generator) quét và phát hiện ra thư mục `k8s_helm/*` trên nhánh `dev` vừa có mã SHA commit mới.

### Bước 4: Đối chiếu trạng thái (Diff / Compare)
Sau khi lấy mã nguồn mới, ArgoCD tiến hành so sánh (Diff) giữa 2 bản đối chiếu:
1. **Desired State (Trạng thái mong muốn):** Đọc từ thư mục `k8s_helm` kết hợp với `values-dev.yaml` mới nhất trên Git.
2. **Live State (Trạng thái thực tế):** Lấy trực tiếp từ API của cụm Kubernetes (Cluster Dev).
*Kết quả:* Khi ArgoCD phát hiện sự khác biệt (ví dụ: trên Git yêu cầu sửa port thành 8080, nhưng trên Cụm đang là 80), trạng thái của ứng dụng lập tức chuyển sang màu vàng **`OutOfSync`**.

### Bước 5: Đồng bộ thủ công qua bảng lệnh CLI (Manual Sync)
Theo thiết kế chuẩn Enterprise, chúng ta **tắt chế độ Auto-Sync (tắt prune/selfHeal)** trên môi trường Dev/Prod để kỹ sư có quyền kiểm soát thời điểm release (Kiểm soát Zero-Downtime, Rolling Update).
Thay vì để ArgoCD tự động chạy theo Git, chúng ta sẽ quản lý bằng tay qua CLI:

**Kịch bản 1: Dev push code mới**
- Hệ thống CI build image → push tag mới lên Registry.
- ArgoCD Image Updater phát hiện có tag mới → tự động đẩy một Git commit ẩn để update thông số image tag vào trong branch.
- ArgoCD phát hiện ra `OutOfSync` nhưng **KHÔNG** tự update.
- Kỹ sư / Pipeline Script tiến hành chạy lệnh Sync thủ công qua CLI:
  ```bash
  argocd app sync meo-station-backend-dev
  ```
- *Hành vi của ArgoCD:* Nó sẽ tiến hành Rolling Update. Tạo Pod mới với version mới, chờ Pod mới `Ready` thì bắt đầu Terminate Pod cũ một cách từ từ để đảm bảo **Zero Downtime**.

### Bước 6: Phản hồi và Kịch bản Rollback (Manual Rollback qua CLI)
Sau khi ứng dụng đã Sync thành công (chuyển sang `Healthy`), mọi thứ hoạt động bình thường. Tuy nhiên, nếu version mới vừa đẩy lên gặp lỗi (ví dụ: CrashLoopBackOff), kỹ sư cần Rollback ngay lập tức.

**Kịch bản 4: Rollback về Version cũ**
ArgoCD lưu trữ toàn bộ History (lịch sử) các bản release của bạn. Để rollback nhanh gọn không cần chờ đợi sửa code trên Git:

1. **Xem lịch sử các bản Deploy (History):**
   ```bash
   argocd app history meo-station-backend-dev
   ```
   *(Kết quả sẽ in ra ID của các bản deploy trước đó, ví dụ ID=5 là bản v1.2.3 chạy ổn định, ID=6 là bản v1.2.4 bị lỗi).*

2. **Thực thi Rollback nóng qua CLI:**
   ```bash
   argocd app rollback meo-station-backend-dev 5
   ```
- *Hành vi của ArgoCD:* Nó sẽ lập tức huỷ bỏ các Pod của version hiện tại và khôi phục lại các Pod về đúng trạng thái cấu hình của History ID=5 (Deploy lại đúng version cũ từ Git history).
- *Cách xử lý tiếp theo:* Sau khi Prod đã an toàn với bản cũ, quy trình đúng là Developer sẽ phải sửa lại tham số `targetRevision` hoặc image tag về bản ổn định trên file `values-prod.yaml` → Tạo Pull Request → Merge → Sync lại để gỡ cờ báo dơ `OutOfSync` trên ArgoCD.

---

## 🐋 Mở rộng: Luồng GitOps khi Push Image (ArgoCD Image Updater)
Trong trường hợp Developer không sửa code Helm mà chỉ lập trình ra chức năng mới và Build thành Docker Image mới, quy trình sẽ được mở rộng bởi một "cánh tay nối dài":

1. Hệ thống CI build ra Docker Image (ví dụ `meo-backend:v1.2.0`) và đẩy lên Docker Hub.
2. Thiết bị theo dõi **ArgoCD Image Updater** phát hiện kho Docker Hub vừa ra version `v1.2.0`.
3. Thay vì kêu Developer vào đổi file YAML, Image Updater tự động gọi API đẩy một commit ẩn lên Git Repository của bạn để ghi đè tham số hình ảnh thành `v1.2.0`.
4. Sau khi Github được cập nhật version mới, chu trình ngay lập tức quay lại **Bước 3** và ArgoCD sẽ tiếp tục Deploy phiên bản code mới này ra cụm thật một cách tự động 100%.
