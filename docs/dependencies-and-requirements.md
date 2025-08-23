# CBX MCP Server K8s - Dependencies & Requirements

This document outlines all the dependency resources and requirements needed for the cbx-mcp-server-k8s to work properly in a Kubernetes cluster.

## 🔧 Required Kubernetes Resources

### 1. Secrets (Must exist before deployment)

NOTE: TODO: separate ArgoCD token into separate secret and keep the rest in configmap

The MCP server requires these secrets to be created manually:

```bash
# Kubeconfig Secret
kubectl create secret generic cbx-mcp-k8s-kubeconfig \
  --from-file=config=~/.kube/config \
  -n cbx-mcp-servers

# ArgoCD Config Secret
kubectl create secret generic cbx-mcp-k8s-argocd-config \
  --from-file=config=~/.config/argocd/config \
  -n cbx-mcp-servers
```

**Secret Requirements:**
- **Namespace:** `cbx-mcp-servers` (or target deployment namespace)
- **Secret Names:** Must match values in `secretReferences`
- **Key Names:** Must be `config` for kubeconfig and `config` for ArgoCD
- **File Content:** Valid kubeconfig and ArgoCD configuration files

### 2. Namespace

```bash
# Create namespace if it doesn't exist
kubectl create namespace cbx-mcp-servers
```

### 3. RBAC Permissions (Recommended)

The MCP server needs appropriate permissions to execute kubectl commands:

```yaml
# Create ServiceAccount, ClusterRole, and ClusterRoleBinding
apiVersion: v1
kind: ServiceAccount
metadata:
  name: cbx-mcp-k8s-sa
  namespace: cbx-mcp-servers
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: cbx-mcp-k8s-cluster-role
rules:
- apiGroups: [""]
  resources: ["*"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["apps"]
  resources: ["*"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["networking.k8s.io"]
  resources: ["*"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: cbx-mcp-k8s-cluster-role-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cbx-mcp-k8s-cluster-role
subjects:
- kind: ServiceAccount
  name: cbx-mcp-k8s-sa
  namespace: cbx-mcp-servers
```

## 🌐 Network & Infrastructure Requirements

### 4. Ingress Controller (Optional for External Access)

If you want external access to the MCP server, ensure nginx ingress controller is installed:

```bash
# Check if nginx ingress exists
kubectl get pods -n ingress
kubectl get svc -n ingress

# Should see nginx-ingress service with LoadBalancer/External IP
```

### 5. DNS Configuration (Optional for External Access)

If using external access, domain must resolve to the ingress controller's external IP:

```bash
# Your domain should resolve to ingress IP
nslookup cbx-mcp-k8s.vvklab.cloud.cembryonix.com
# Should return the ingress LoadBalancer IP (e.g., 10.0.0.200)
```

## 📋 Complete Pre-Installation Checklist

### Required Before Helm Install:

```bash
# 1. Create namespace
kubectl create namespace cbx-mcp-servers

# 2. Create kubeconfig secret
kubectl create secret generic cbx-mcp-k8s-kubeconfig \
  --from-file=config=~/.kube/config \
  -n cbx-mcp-servers

# 3. Create ArgoCD config secret (if you have ArgoCD)
kubectl create secret generic cbx-mcp-k8s-argocd-config \
  --from-file=config=~/.config/argocd/config \
  -n cbx-mcp-servers

# 4. Apply RBAC permissions (recommended)
kubectl apply -f rbac.yaml

# 5. Verify ingress controller (if using external access)
kubectl get svc -n ingress nginx-ingress

# 6. Configure DNS (if using external access)
# Point cbx-mcp-k8s.your-domain.com → INGRESS_EXTERNAL_IP
```

### Verification Commands:

```bash
# Verify all dependencies before install
kubectl get secrets -n cbx-mcp-servers | grep cbx-mcp-k8s
kubectl get serviceaccount cbx-mcp-k8s-sa -n cbx-mcp-servers
kubectl get clusterrolebinding cbx-mcp-k8s-cluster-role-binding
kubectl get svc -n ingress  # if using external access
nslookup cbx-mcp-k8s.your-domain.com  # if using external access
```

## 🎯 Installation Examples

### Minimal Installation (Internal Access Only):

```bash
# Step 1: Create namespace and secrets
kubectl create namespace cbx-mcp-servers

kubectl create secret generic cbx-mcp-k8s-kubeconfig \
  --from-file=config=~/.kube/config \
  -n cbx-mcp-servers

kubectl create secret generic cbx-mcp-k8s-argocd-config \
  --from-file=config=~/.config/argocd/config \
  -n cbx-mcp-servers

# Step 2: Install with custom values (ingress disabled)
helm install cbx-mcp-k8s ./cbx-mcp-server-k8s \
  -n cbx-mcp-servers \
  --set ingress.enabled=false
```

### Full Installation (External Access):

```bash
# Step 1: Create all dependencies (including RBAC)
kubectl create namespace cbx-mcp-servers
kubectl apply -f rbac.yaml

kubectl create secret generic cbx-mcp-k8s-kubeconfig \
  --from-file=config=~/.kube/config \
  -n cbx-mcp-servers

kubectl create secret generic cbx-mcp-k8s-argocd-config \
  --from-file=config=~/.config/argocd/config \
  -n cbx-mcp-servers

# Step 2: Install with custom values
helm install cbx-mcp-k8s ./cbx-mcp-server-k8s \
  -n cbx-mcp-servers \
  -f values-custom.yaml
```

## ⚠️ Common Issues & Solutions

### If kubeconfig secret doesn't exist:
```
MountVolume.SetUp failed for volume "kubeconfig" : secret "cbx-mcp-k8s-kubeconfig" not found
```
**Solution:** Create the kubeconfig secret using the command in section 1.

### If ArgoCD config secret doesn't exist:
```
MountVolume.SetUp failed for volume "argocd-config" : secret "cbx-mcp-k8s-argocd-config" not found
```
**Solution:** Create the ArgoCD config secret, or create an empty secret if ArgoCD is not used:
```bash
kubectl create secret generic cbx-mcp-k8s-argocd-config \
  --from-literal=config="" \
  -n cbx-mcp-servers
```

### If RBAC permissions are insufficient:
```
Error: User "system:serviceaccount:cbx-mcp-servers:default" cannot list pods
```
**Solution:** Apply the RBAC configuration from section 3, or update your deployment to use the created ServiceAccount.

### If ConfigMap creation fails:
```
Error: configmap "cbx-mcp-k8s-config" could not be created
```
**Solution:** Ensure the `config` value in values.yaml is properly formatted YAML.

### If ingress is not accessible:
```
curl: (6) Could not resolve host: cbx-mcp-k8s.your-domain.com
```
**Solution:** Configure DNS records or disable ingress for internal-only access.

## 🔒 Security Considerations

### Kubeconfig Security:
- **Use limited kubeconfig:** Create a kubeconfig with minimal required permissions
- **Namespace-scoped:** Consider using a kubeconfig scoped to specific namespaces
- **Regular rotation:** Rotate kubeconfig credentials regularly

### ArgoCD Security:
- **Read-only access:** Use ArgoCD config with read-only permissions when possible
- **Secure credentials:** Ensure ArgoCD config doesn't contain sensitive tokens

### Network Security:
- **Internal access:** Consider using ClusterIP only for internal agent access
- **Network policies:** Implement network policies to restrict traffic
- **TLS termination:** Use TLS for external ingress access

## 📚 Configuration Options

### MCP Server Configuration (values.yaml):

```yaml
config: |
  server:
    server_name: "cbx-mcp-k8s-server"
    transport_type: "http"
    host: "0.0.0.0"
    port: 8080
    log_level: "INFO"
  
  command:
    default_timeout: 120
    max_output_size: 100000
  
  security:
    security_config_path: None
    security_mode: "strict"  # strict or permissive
```

### Service Access Patterns:

**Internal Agent Access (Recommended):**
```yaml
service:
  name: cbx-mcp-k8s
  type: ClusterIP
  
ingress:
  enabled: false
```

**External API Access:**
```yaml
service:
  name: cbx-mcp-k8s
  type: ClusterIP
  
ingress:
  enabled: true
  host: cbx-mcp-k8s.your-domain.com
```

## 🚀 Next Steps

After successful installation:
1. **Test MCP server:** Use the provided test commands to verify functionality
2. **Configure agent:** Update your CBX Agent to connect to this MCP server
3. **Monitor logs:** Check pod logs for any configuration issues
4. **Security review:** Ensure RBAC and network policies meet your requirements

For more information, refer to the Helm chart documentation and MCP protocol specifications.