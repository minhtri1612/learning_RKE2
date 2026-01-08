# RKE2 Installation Configuration Review

## Summary
Reviewed all Terraform, Ansible, and Helm configurations for Rancher RKE2 installation. Found and fixed several critical and important issues.

## ✅ Fixed Issues

### 1. **CRITICAL: Worker Connection Port (FIXED)**
   - **Issue**: `ansible/worker.yml` was using port `9345` (Supervisor API) instead of `6443` (Kubernetes API Server)
   - **Impact**: Workers would fail to join the cluster since the NLB is configured for port 6443
   - **Fix**: Changed worker config to use port 6443

### 2. **Security: Port 9345 Exposure (FIXED)**
   - **Issue**: Port 9345 (RKE2 Supervisor API) was open to `0.0.0.0/0` in security group
   - **Impact**: Security risk - internal API exposed to internet
   - **Fix**: Restricted port 9345 to VPC CIDR only (`10.0.0.0/16`)

### 3. **Missing Required Ports (FIXED)**
   - **Issue**: Missing ports required for RKE2 cluster communication:
     - Port 10250 (Kubelet API)
     - Port 8472 (Flannel VXLAN)
   - **Impact**: Cluster nodes may not communicate properly
   - **Fix**: Added both ports to security group (restricted to VPC CIDR)

### 4. **Swap Disable Not Persistent (FIXED)**
   - **Issue**: Swap was disabled temporarily but not permanently
   - **Impact**: Swap could be re-enabled after reboot, causing RKE2 issues
   - **Fix**: Added task to disable swap in `/etc/fstab` permanently

### 5. **PATH Not Persistent (FIXED)**
   - **Issue**: RKE2 bin path export was not persistent in init-cluster.yaml
   - **Impact**: kubectl commands would fail after logout/login
   - **Fix**: Added PATH export to `.bashrc` for ubuntu user

### 6. **Missing API Server Readiness Check (FIXED)**
   - **Issue**: No verification that API server is ready before proceeding
   - **Impact**: Subsequent steps might fail if API server isn't ready
   - **Fix**: Added health check wait task

## ⚠️ Recommendations (Not Critical)

### 1. **Storage Class Configuration**
   - **Current**: Using `local-path-provisioner` (installed via deploy.py)
   - **Observation**: IAM role has EBS CSI driver policy attached, but EBS CSI driver is not installed
   - **Recommendation**: 
     - Option A: Remove EBS CSI policy if not using EBS volumes
     - Option B: Install EBS CSI driver if you want to use EBS volumes (better for production)

### 2. **Spot Instances**
   - **Current**: Using spot instances for both masters and workers
   - **Risk**: Spot instances can be terminated, causing cluster instability
   - **Recommendation**: Consider using on-demand instances for master nodes (or at least one master)

### 3. **Hardcoded Token**
   - **Current**: Token is hardcoded as "MySuperSecretToken123"
   - **Recommendation**: Generate a secure random token and store it securely

### 4. **Single Master Node**
   - **Current**: Only 1 master node configured
   - **Risk**: No high availability - single point of failure
   - **Recommendation**: For production, use at least 3 master nodes for HA

### 5. **Missing etcd Backup Configuration**
   - **Recommendation**: Add etcd backup configuration for disaster recovery

## ✅ Correctly Configured

1. **Terraform Infrastructure**
   - VPC and networking properly configured
   - Security groups have required ports for RKE2
   - NLB correctly configured for API server (port 6443)
   - IAM roles and instance profiles set up correctly

2. **Ansible Playbooks**
   - System preparation (kernel modules, sysctl) is correct
   - RKE2 installation commands are correct
   - Master node configuration includes TLS SAN for NLB DNS

3. **Helm Charts**
   - Database StatefulSet properly configured
   - Storage class configuration is flexible
   - Secrets and services are correctly templated

## Files Modified

1. `ansible/worker.yml` - Fixed worker connection port
2. `terraform/vpc.tf` - Improved security group rules
3. `ansible/all.yaml` - Made swap disable persistent
4. `ansible/init-cluster.yaml` - Added PATH persistence and API readiness check

## Testing Recommendations

1. Test worker node joining after the port fix
2. Verify cluster communication with all required ports
3. Test storage provisioning with local-path-provisioner
4. Verify kubectl works after logout/login
5. Test cluster after reboot to ensure swap stays disabled

## Next Steps

1. Apply the fixes and test the deployment
2. Consider implementing the recommendations for production use
3. Set up monitoring and alerting for the cluster
4. Document the token management process
5. Plan for etcd backups








