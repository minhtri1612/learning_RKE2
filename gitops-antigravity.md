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

### Bước 5: Bắt đầu quá trình đồng bộ (Automated Sync)
Nhờ có cờ sau đây được thiết lập mức cao nhất trong file ApplicationSet:
```yaml
syncPolicy:
  automated:
    prune: true
    selfHeal: true
```
ArgoCD tự động kích hoạt tính năng **Auto-Sync**:
- Nó sử dụng chìa khóa xác thực trong file `cluster-dev.yaml` để kết nối API của Cụm K8s Dev.
- Ra lệnh đè cấu hình mới cho Kubernetes: "Cập nhật ứng dụng Mèo Station Backend sang port 8080".
- *Lưu ý về Self-Heal:* Nếu ai đó lén dùng tay thay đổi cấu hình trực tiếp trên K8s mà không thông qua Git, ArgoCD sẽ coi đó là "lệch chuẩn" và ngay lập tức vả lại trạng thái cho giống hệt với Git.
- *Lưu ý về Prune:* Nếu tài nguyên nào đó bị xoá trên Git, ArgoCD cũng sẽ tự động dỡ bỏ nó khỏi cụm K8s.

### Bước 6: Phản hồi và hoàn tất (Healthy & Synced)
- Sau khi Kubernetes thay đổi cấu hình xong, các Pods mới quay sang trạng thái hoạt động bình thường (`Running`).
- ArgoCD đánh giá trạng thái ứng dụng chuyển thành màu xanh **`Healthy`** và **`Synced`**.
- Nếu có cấu hình hệ thống `argocd-notifications`, lúc này nó sẽ bắn cảnh báo thành công qua Webhook về kênh Slack, Teams hoặc Email cho Developer biết *"Deploy Thành Công!"*.

---

## 🐋 Mở rộng: Luồng GitOps khi Push Image (ArgoCD Image Updater)
Trong trường hợp Developer không sửa code Helm mà chỉ lập trình ra chức năng mới và Build thành Docker Image mới, quy trình sẽ được mở rộng bởi một "cánh tay nối dài":

1. Hệ thống CI build ra Docker Image (ví dụ `meo-backend:v1.2.0`) và đẩy lên Docker Hub.
2. Thiết bị theo dõi **ArgoCD Image Updater** phát hiện kho Docker Hub vừa ra version `v1.2.0`.
3. Thay vì kêu Developer vào đổi file YAML, Image Updater tự động gọi API đẩy một commit ẩn lên Git Repository của bạn để ghi đè tham số hình ảnh thành `v1.2.0`.
4. Sau khi Github được cập nhật version mới, chu trình ngay lập tức quay lại **Bước 3** và ArgoCD sẽ tiếp tục Deploy phiên bản code mới này ra cụm thật một cách tự động 100%.
