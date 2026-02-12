# GitHub Two-User Setup (Dev + Admin)

Hướng dẫn setup 2 GitHub accounts để phân quyền dev không được push vào prod (main branch).

---

## Tổng quan

| User | GitHub Account | Git Access | ArgoCD RBAC |
|------|---------------|------------|-------------|
| **Admin** | `minhtri1612` (owner) | Push dev + main | admin role |
| **Dev** | Account mới (collaborator) | Push dev only | dev-user role |

---

## Bước 1: Tạo GitHub account cho Dev

### Option A: Tạo account GitHub mới
1. Vào https://github.com/signup
2. Tạo account mới, ví dụ: `minhtri-dev` hoặc dùng email khác
3. Verify email

### Option B: Dùng account GitHub có sẵn
- Nếu bạn có account GitHub khác, dùng luôn

**Giả sử dev account là: `minhtri-dev`**

---

## Bước 2: Add Dev user vào repo (làm từ Admin account)

### 2.1 Add Collaborator

1. Vào repo: https://github.com/minhtri1612/learning_RKE2
2. Settings → Collaborators and teams
3. Click "Add people"
4. Nhập username: `minhtri-dev` (hoặc email của dev user)
5. Select permission: **Write** (cho phép push code)
6. Send invitation

### 2.2 Dev user accept invitation

1. Dev user check email hoặc vào: https://github.com/minhtri1612/learning_RKE2
2. Click "Accept invitation"

---

## Bước 3: Setup GitHub Branch Protection (Admin làm)

### 3.1 Vào Branch Protection Settings

```
https://github.com/minhtri1612/learning_RKE2/settings/branches
```

### 3.2 Add Rule cho `main` branch

**Branch name pattern:** `main`

**Protection settings:**

✅ **Require a pull request before merging**
  - Require approvals: `1`
  - ☑ Dismiss stale pull request approvals when new commits are pushed
  - ☑ Require review from Code Owners (optional)

✅ **Require conversation resolution before merging**

✅ **Require linear history** (optional, giữ history sạch)

✅ **Do not allow bypassing the above settings**
  - ☑ Include administrators (quan trọng! Admin cũng phải follow rules)

✅ **Restrict who can push to matching branches**
  - ☑ Enable
  - **Add people:** `minhtri1612` (admin only)
  - **NOT add:** `minhtri-dev` (dev user không được push trực tiếp)

✅ **Allow force pushes:** DISABLE (ngăn force push phá history)

✅ **Allow deletions:** DISABLE (ngăn xóa branch)

### 3.3 Save changes

Click **"Create"** hoặc **"Save changes"**

---

## Bước 4: Optional - Protect `dev` branch

Nếu muốn ngăn dev force push hoặc xóa dev branch:

**Branch name pattern:** `dev`

**Settings (nhẹ hơn main):**
- ☑ Allow force pushes: DISABLE
- ☑ Allow deletions: DISABLE
- Không cần require PR (dev push trực tiếp vào dev OK)

---

## Bước 5: Setup Git cho Dev User (trên máy dev)

### 5.1 Clone repo với dev account

```bash
# Remove repo cũ nếu có
rm -rf ~/learning_RKE2

# Clone lại với HTTPS để dễ switch accounts
git clone https://github.com/minhtri1612/learning_RKE2.git
cd learning_RKE2

# Config dev user identity
git config user.name "minhtri-dev"
git config user.email "dev-email@example.com"
```

### 5.2 Setup authentication cho dev account

**Option A: HTTPS with Personal Access Token (Recommended)**

```bash
# Dev user tạo Personal Access Token:
# https://github.com/settings/tokens
# → Generate new token (classic)
# → Scopes: repo (full control)
# → Generate token
# → Copy token (ghp_xxxxxxxxxxxx)

# Khi push lần đầu, Git sẽ hỏi username/password:
git push
# Username: minhtri-dev
# Password: ghp_xxxxxxxxxxxx (paste token)

# Git sẽ cache credentials
```

**Option B: SSH Key (Advanced)**

```bash
# Dev user generate SSH key riêng
ssh-keygen -t ed25519 -C "dev-email@example.com" -f ~/.ssh/id_ed25519_dev

# Add public key vào GitHub dev account:
# https://github.com/settings/keys
cat ~/.ssh/id_ed25519_dev.pub
# → Copy & add to GitHub

# Config SSH để dùng key riêng
vim ~/.ssh/config
```

Add vào `~/.ssh/config`:

```
Host github.com-dev
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_dev
```

Update remote URL:

```bash
cd ~/learning_RKE2
git remote set-url origin git@github.com-dev:minhtri1612/learning_RKE2.git
```

---

## Bước 6: Test Workflow

### Test 1: Dev push vào `dev` branch ✅ (OK)

```bash
# Dev user
cd ~/learning_RKE2
git checkout dev
git pull origin dev

# Sửa file
vim k8s_helm/backend/values-dev.yaml
# Thay replicas: 2 → replicas: 4

git add .
git commit -m "Update dev replicas to 4"
git push origin dev

# → SUCCESS (dev được push vào dev branch)
# → ArgoCD dev tự sync sau 3-5 phút
```

### Test 2: Dev try push vào `main` branch ❌ (FAIL)

```bash
# Dev user
git checkout main
git pull origin main

# Sửa prod file
vim k8s_helm/backend/values-prod.yaml
# Thay replicas

git add .
git commit -m "Try update prod"
git push origin main

# → EXPECTED ERROR:
# remote: error: GH006: Protected branch update failed
# remote: error: Required status checks failed
# remote: error: User minhtri-dev is not allowed to push to main
```

**Kết quả:** ❌ GitHub reject! Dev không thể push trực tiếp vào main.

### Test 3: Dev tạo PR ✅ (OK, nhưng cần admin approve)

```bash
# Dev user đã push changes vào dev branch

# Vào GitHub UI:
# https://github.com/minhtri1612/learning_RKE2/compare/main...dev

# Create Pull Request:
# Title: "Update backend replicas for prod"
# Description: "Increase replicas from 2 to 4"
# → Create pull request

# → PR created, status: "Waiting for review"
# → Prod CHƯA update (chưa merged)
```

### Test 4: Admin review & merge PR

```bash
# Admin (minhtri1612) vào GitHub:
# https://github.com/minhtri1612/learning_RKE2/pulls

# Click vào PR
# → Review changes
# → Files changed: check diff
# → Review required (1 approval)

# Admin approve:
# → "Approve"
# → "Merge pull request"
# → "Confirm merge"

# → PR merged vào main
# → ArgoCD prod tự sync sau 3-5 phút
```

### Test 5: Verify ArgoCD sync đúng branch

```bash
# Check dev app
argocd app get meo-station-backend-dev --grpc-web | grep -E "Target|Status"
# Target: dev
# Sync Status: Synced

# Check prod app
argocd app get meo-station-backend-prod --grpc-web | grep -E "Target|Status"
# Target: main
# Sync Status: Synced
```

---

## Workflow Summary

### Dev User Workflow

```
1. git checkout dev
2. vim k8s_helm/backend/values-dev.yaml
3. git commit -m "Update dev"
4. git push origin dev
   → ArgoCD dev tự sync

5. Khi muốn deploy lên prod:
   - Vào GitHub UI
   - Create PR: dev → main
   - Đợi admin approve
   - Admin merge → ArgoCD prod sync
```

### Admin User Workflow

```
1. Review PRs từ dev
2. Check changes trên dev cluster trước
3. Approve PR nếu OK
4. Merge PR
   → ArgoCD prod tự sync
```

---

## Permissions Matrix

| Action | Dev User | Admin User |
|--------|----------|-----------|
| Push vào `dev` branch | ✅ Allowed | ✅ Allowed |
| Push vào `main` branch | ❌ Blocked | ❌ Blocked (phải qua PR) |
| Tạo PR `dev → main` | ✅ Allowed | ✅ Allowed |
| Approve PR | ❌ Blocked | ✅ Allowed |
| Merge PR | ❌ Blocked | ✅ Allowed |
| ArgoCD sync dev apps | ❌ Blocked (RBAC) | ✅ Allowed |
| ArgoCD sync prod apps | ❌ Blocked (RBAC) | ✅ Allowed |
| SSH vào dev nodes | ✅ Allowed (VPN minhtri.ovpn) | ✅ Allowed |
| SSH vào prod nodes | ❌ Blocked (iptables) | ✅ Allowed (VPN sep_tong.ovpn) |

---

## Troubleshooting

### Dev vẫn push được vào main

→ Check branch protection: https://github.com/minhtri1612/learning_RKE2/settings/branches
→ Verify "Restrict who can push" đã enable và chỉ add admin

### Dev không push được vào dev

→ Check collaborator permissions: https://github.com/minhtri1612/learning_RKE2/settings/access
→ Dev user cần role "Write" hoặc cao hơn

### Authentication failed khi push

→ Check Git credentials:
```bash
git config user.name
git config user.email
git config credential.helper
```

→ Re-authenticate:
```bash
# HTTPS: remove cached credentials
git credential-cache exit
# Push lại và nhập credentials mới

# SSH: check key
ssh -T git@github.com
```

### ArgoCD không sync từ đúng branch

```bash
# Check application YAML
kubectl get application meo-station-backend-dev -n argocd -o yaml | grep targetRevision
# Should show: targetRevision: dev

kubectl get application meo-station-backend-prod -n argocd -o yaml | grep targetRevision
# Should show: targetRevision: main
```

Nếu sai:
```bash
cd ~/Downloads/practice_RKE2
./scripts/setup-argocd-management-apps.sh
```

---

## Rollback hoặc Emergency Fix

Nếu prod bị lỗi nghiêm trọng và cần hotfix ngay:

**Option 1: Admin tạo hotfix branch**
```bash
git checkout main
git pull origin main
git checkout -b hotfix/critical-bug

# Fix bug
vim k8s_helm/backend/...
git commit -m "Hotfix: ..."
git push origin hotfix/critical-bug

# Create PR hotfix → main
# Admin approve & merge nhanh
```

**Option 2: Admin force merge (emergency only)**
```bash
# Nếu đã enable "Include administrators" trong branch protection
# → Admin KHÔNG thể push trực tiếp, phải qua PR

# Để bypass trong emergency:
# 1. Tạm tắt branch protection
# 2. Push trực tiếp
# 3. Bật lại branch protection
# (NOT RECOMMENDED - chỉ dùng trong tình huống cực kỳ khẩn cấp)
```

---

## Summary Checklist

✅ Tạo GitHub account cho dev user
✅ Add dev user làm collaborator (Write permission)
✅ Setup branch protection cho `main`:
  - Require PR
  - Require approval (1)
  - Restrict push to admin only
  - Include administrators
✅ Dev user clone repo và config Git
✅ Test: dev push vào dev → OK
✅ Test: dev push vào main → FAIL
✅ Test: dev tạo PR → OK, cần admin approve
✅ Test: admin approve & merge PR → prod update

---

## Next Steps

Sau khi setup xong GitHub, bạn có **2 layers phân quyền**:

1. **Git Layer (GitHub Branch Protection)**
   - Dev chỉ push vào `dev` branch
   - Main branch bảo vệ bởi PR workflow

2. **ArgoCD RBAC Layer**
   - dev-user không manual sync prod apps
   - Auto-sync vẫn hoạt động khi PR merged

3. **Network Layer (VPN + iptables)**
   - minhtri.ovpn: access dev network only
   - sep_tong.ovpn: access all networks

**Kết hợp 3 layers → Phân quyền chặt chẽ dev/prod!**
