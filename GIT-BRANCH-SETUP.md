# Git Branch Strategy Setup Guide

Hướng dẫn setup Git branch strategy để phân quyền dev/prod qua Git + ArgoCD.

---

## Tổng quan

**Mục tiêu:** Dev push vào `dev` branch, chỉ admin merge vào `main` (prod).

```
learning_RKE2 repo:
├── main (protected)   ← Prod ArgoCD sync từ đây
└── dev                ← Dev ArgoCD sync từ đây, dev push vào đây
```

---

## Bước 1: Tạo dev branch trong learning_RKE2 repo

```bash
# Clone learning_RKE2 repo (nếu chưa có)
git clone https://github.com/minhtri1612/learning_RKE2.git
cd learning_RKE2

# Tạo dev branch từ main
git checkout main
git pull origin main
git checkout -b dev
git push -u origin dev

# Verify
git branch -a
# Should see: remotes/origin/dev
```

---

## Bước 2: Update ArgoCD values (ĐÃ XONG)

✅ `argocd/applications/overlays/dev/values.yaml` - targetRevision: dev
✅ `argocd/applications/overlays/prod/values.yaml` - targetRevision: main

---

## Bước 3: Deploy lại ArgoCD Applications

```bash
cd ~/Downloads/practice_RKE2

# Set KUBECONFIG (nếu chưa)
export KUBECONFIG=/home/minhtri/Downloads/practice_RKE2/.kube_config_rke2_management_tunnel.yaml

# Deploy với target revisions mới
./scripts/setup-argocd-management-apps.sh
```

**Kết quả:**
- Dev apps sync từ `dev` branch
- Prod apps sync từ `main` branch

---

## Bước 4: GitHub Branch Protection

### 4.1 Vào GitHub Settings

```
https://github.com/minhtri1612/learning_RKE2/settings/branches
```

### 4.2 Add branch protection rule

**Branch name pattern:** `main`

**Enable:**
- ☑ Require a pull request before merging
  - Require approvals: 1
  - Dismiss stale pull request approvals when new commits are pushed
- ☑ Require conversation resolution before merging
- ☑ Restrict pushes
  - Add people/teams who can push: (Chỉ admin)

**Save changes**

---

## Bước 5: Test workflow

### Test 1: Dev push vào dev branch (OK)

```bash
# Dev user
cd learning_RKE2
git checkout dev

# Sửa dev values
vim k8s_helm/backend/values-dev.yaml
# Thay replicas: 2 → replicas: 3

git add .
git commit -m "Increase dev replicas"
git push origin dev
# ✅ SUCCESS

# Đợi 3-5 phút → ArgoCD dev tự sync
```

---

### Test 2: Dev try push vào main (FAIL)

```bash
# Dev user
git checkout main
git pull origin main

# Sửa prod values
vim k8s_helm/backend/values-prod.yaml
# Thay replicas

git add .
git commit -m "Update prod"
git push origin main
# ❌ GitHub reject: branch is protected
```

---

### Test 3: Dev tạo PR (OK, nhưng cần approval)

```bash
# Dev user đã push vào dev branch

# Vào GitHub UI:
# https://github.com/minhtri1612/learning_RKE2/compare/main...dev

# Click "Create Pull Request"
# Title: "Update prod replicas"
# → PR created, but not merged (waiting admin approval)
```

**Prod CHƯA update** vì PR chưa được merge.

---

### Test 4: Admin approve PR

```bash
# Admin vào GitHub
# https://github.com/minhtri1612/learning_RKE2/pulls

# Review PR
# → Approve
# → Merge pull request

# → ArgoCD prod tự sync trong 3-5 phút
```

---

## Workflow hoàn chỉnh

```
Dev → Push dev branch → ArgoCD dev sync tự động

Dev → Tạo PR dev→main → Admin review → Admin merge → ArgoCD prod sync
```

---

## Verify ArgoCD đang sync đúng branch

```bash
# Check dev app
argocd app get meo-station-backend-dev --grpc-web | grep Target
# Output: Target: dev

# Check prod app
argocd app get meo-station-backend-prod --grpc-web | grep Target
# Output: Target: main
```

---

## Rollback

Nếu muốn quay lại cấu trúc cũ (main cho cả dev + prod):

```bash
# Sửa overlays/dev/values.yaml: targetRevision: main
# Sửa overlays/prod/values.yaml: targetRevision: main
# Deploy lại
```

---

## Troubleshooting

### ArgoCD không sync từ dev branch

```bash
# Check application status
argocd app get meo-station-backend-dev --grpc-web

# Check if dev branch exists
git ls-remote https://github.com/minhtri1612/learning_RKE2.git | grep dev
```

### Dev vẫn push được vào main

→ Branch protection chưa được enable hoặc config sai.

Check: GitHub → Settings → Branches → main protection rules

---

## Summary

✅ ArgoCD values đã update (targetRevision: dev/main)
⏸️ Cần làm thủ công:
  1. Tạo dev branch trong learning_RKE2
  2. Deploy ArgoCD apps (`setup-argocd-management-apps.sh`)
  3. GitHub branch protection
  4. Test workflow
