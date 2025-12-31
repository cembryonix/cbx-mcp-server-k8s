# tests/unit/test_validators.py
"""
Unit tests for security validators.
These tests verify the security validation layer that protects against dangerous commands.
"""

import pytest
from app.cbx_mcp_k8s.executor.validators import (
    is_auth_error,
    get_tool_from_command,
    validate_unix_command,
    is_pipe_command,
    is_safe_exec_command,
    validate_k8s_command,
    validate_pipe_command,
    validate_command,
    is_valid_k8s_tool,
    split_pipe_command,
)


class TestIsAuthError:
    """Tests for authentication error detection."""

    def test_unauthorized_error(self):
        assert is_auth_error("Unauthorized") is True

    def test_forbidden_error(self):
        assert is_auth_error("Error: forbidden") is True

    def test_connection_error(self):
        assert is_auth_error("Unable to connect to the server") is True

    def test_kubeconfig_error(self):
        assert is_auth_error("Invalid kubeconfig") is True

    def test_argocd_login_error(self):
        assert is_auth_error("You must be logged in") is True

    def test_helm_repo_error(self):
        assert is_auth_error("Error: Helm repo authentication failed") is True

    def test_normal_error_not_auth(self):
        assert is_auth_error("pod not found") is False

    def test_case_insensitive(self):
        assert is_auth_error("UNAUTHORIZED") is True
        assert is_auth_error("FORBIDDEN") is True


class TestGetToolFromCommand:
    """Tests for extracting tool name from commands."""

    def test_kubectl_command(self):
        assert get_tool_from_command("kubectl get pods") == "kubectl"

    def test_helm_command(self):
        assert get_tool_from_command("helm list") == "helm"

    def test_argocd_command(self):
        assert get_tool_from_command("argocd app list") == "argocd"

    def test_unknown_tool(self):
        assert get_tool_from_command("istioctl version") is None

    def test_empty_command(self):
        assert get_tool_from_command("") is None

    def test_command_with_quotes(self):
        assert get_tool_from_command('kubectl get pods -l "app=nginx"') == "kubectl"


class TestValidateUnixCommand:
    """Tests for Unix command validation in pipes."""

    def test_allowed_grep(self):
        assert validate_unix_command("grep pattern") is True

    def test_allowed_jq(self):
        assert validate_unix_command("jq '.items'") is True

    def test_allowed_head(self):
        assert validate_unix_command("head -n 10") is True

    def test_disallowed_rm(self):
        # rm is commented out in the config
        assert validate_unix_command("rm -rf /") is False

    def test_disallowed_python(self):
        assert validate_unix_command("python -c 'import os'") is False

    def test_empty_command(self):
        assert validate_unix_command("") is False


class TestIsPipeCommand:
    """Tests for pipe detection in commands."""

    def test_simple_pipe(self):
        assert is_pipe_command("kubectl get pods | grep nginx") is True

    def test_multiple_pipes(self):
        assert is_pipe_command("kubectl get pods | grep nginx | wc -l") is True

    def test_no_pipe(self):
        assert is_pipe_command("kubectl get pods") is False

    def test_pipe_in_single_quotes(self):
        # Pipe inside quotes should not be detected
        assert is_pipe_command("kubectl get pods -l 'app|web'") is False

    def test_pipe_in_double_quotes(self):
        assert is_pipe_command('kubectl get pods -l "app|web"') is False

    def test_pipe_outside_quotes(self):
        assert is_pipe_command('kubectl get pods -l "app=web" | grep Running') is True


class TestIsSafeExecCommand:
    """Tests for kubectl exec safety validation."""

    def test_non_exec_command(self):
        """Non-exec commands should always be safe."""
        assert is_safe_exec_command("kubectl get pods") is True

    def test_exec_help(self):
        """Help should be safe."""
        assert is_safe_exec_command("kubectl exec --help") is True

    def test_interactive_shell(self):
        """Interactive shell with -it is safe (user knows what they're doing)."""
        assert is_safe_exec_command("kubectl exec -it pod-name -- bash") is True

    def test_shell_with_command(self):
        """Shell with -c flag is safe (specific command)."""
        assert is_safe_exec_command("kubectl exec pod-name -- bash -c 'ls -la'") is True

    def test_unsafe_shell_no_flags(self):
        """Shell without -it or -c is unsafe (opens general shell)."""
        assert is_safe_exec_command("kubectl exec pod-name -- bash") is False

    def test_unsafe_sh_shell(self):
        """sh shell without flags is unsafe."""
        assert is_safe_exec_command("kubectl exec pod-name -- sh") is False

    def test_specific_command_safe(self):
        """Specific commands (not shells) are safe."""
        assert is_safe_exec_command("kubectl exec pod-name -- ls") is True

    def test_exec_with_namespace(self):
        """Exec with namespace and -it is safe."""
        assert is_safe_exec_command("kubectl exec -it -n default pod-name -- /bin/bash") is True


class TestValidateK8sCommand:
    """Tests for Kubernetes command validation."""

    def test_safe_get_command(self, strict_security_mode):
        """Basic get commands should pass."""
        validate_k8s_command("kubectl get pods")  # Should not raise

    def test_dangerous_delete_blocked(self, strict_security_mode):
        """Bare delete should be blocked."""
        with pytest.raises(ValueError, match="restricted"):
            validate_k8s_command("kubectl delete")

    def test_safe_delete_pod_allowed(self, strict_security_mode):
        """Delete with specific resource type should be allowed."""
        validate_k8s_command("kubectl delete pod nginx")  # Should not raise

    def test_delete_all_blocked(self, strict_security_mode):
        """Delete --all should be blocked by regex rule."""
        with pytest.raises(ValueError, match="Deleting all resources"):
            validate_k8s_command("kubectl delete pods --all")

    def test_delete_all_namespaces_blocked(self, strict_security_mode):
        """Delete --all-namespaces should be blocked."""
        with pytest.raises(ValueError, match="all namespaces"):
            validate_k8s_command("kubectl get pods --all-namespaces")

    def test_kube_system_blocked(self, strict_security_mode):
        """Operations in kube-system namespace should be blocked."""
        with pytest.raises(ValueError, match="kube-system"):
            validate_k8s_command("kubectl delete pods --namespace=kube-system")

    def test_empty_command_raises(self, strict_security_mode):
        """Empty command should raise error."""
        with pytest.raises(ValueError, match="Empty command"):
            validate_k8s_command("")

    def test_invalid_tool_raises(self, strict_security_mode):
        """Unknown tool should raise error."""
        with pytest.raises(ValueError, match="supported CLI tool"):
            validate_k8s_command("istioctl version")

    def test_command_without_action_raises(self, strict_security_mode):
        """Command without action should raise error."""
        with pytest.raises(ValueError, match="must include"):
            validate_k8s_command("kubectl")

    def test_helm_uninstall_blocked(self, strict_security_mode):
        """Helm uninstall should be blocked."""
        with pytest.raises(ValueError, match="restricted"):
            validate_k8s_command("helm uninstall release-name")

    def test_helm_uninstall_help_allowed(self, strict_security_mode):
        """Helm uninstall --help should be allowed."""
        validate_k8s_command("helm uninstall --help")  # Should not raise

    def test_argocd_delete_blocked(self, strict_security_mode):
        """ArgoCD app delete should be blocked."""
        with pytest.raises(ValueError, match="restricted"):
            validate_k8s_command("argocd app delete my-app")

    def test_unsafe_exec_blocked(self, strict_security_mode):
        """Unsafe exec should be blocked."""
        with pytest.raises(ValueError, match="Interactive shells"):
            validate_k8s_command("kubectl exec pod-name -- bash")

    def test_permissive_mode_allows_all(self, permissive_security_mode):
        """In permissive mode, all commands should pass."""
        validate_k8s_command("kubectl delete pods --all")  # Should not raise
        validate_k8s_command("kubectl exec pod-name -- bash")  # Should not raise


class TestValidatePipeCommand:
    """Tests for piped command validation."""

    def test_simple_pipe(self, strict_security_mode):
        """Simple pipe with allowed commands."""
        validate_pipe_command("kubectl get pods | grep Running")  # Should not raise

    def test_multiple_pipes(self, strict_security_mode):
        """Multiple pipes with allowed commands."""
        validate_pipe_command("kubectl get pods | grep Running | wc -l")  # Should not raise

    def test_pipe_with_jq(self, strict_security_mode):
        """Pipe with jq for JSON processing."""
        validate_pipe_command("kubectl get pods -o json | jq '.items[]'")  # Should not raise

    def test_disallowed_pipe_command(self, strict_security_mode):
        """Pipe with disallowed command should fail."""
        with pytest.raises(ValueError, match="not allowed"):
            validate_pipe_command("kubectl get pods | python -c 'print(1)'")

    def test_dangerous_first_command(self, strict_security_mode):
        """Dangerous first command should fail even in pipe."""
        with pytest.raises(ValueError, match="restricted"):
            validate_pipe_command("kubectl delete pods --all | wc -l")

    def test_empty_pipe_segment(self, strict_security_mode):
        """Empty pipe segment should fail."""
        with pytest.raises(ValueError, match="Empty command"):
            validate_pipe_command("kubectl get pods |  | wc -l")


class TestValidateCommand:
    """Tests for centralized command validation."""

    def test_simple_command(self, strict_security_mode):
        """Simple command should be validated as k8s command."""
        validate_command("kubectl get pods")  # Should not raise

    def test_pipe_command(self, strict_security_mode):
        """Pipe command should be validated as pipe command."""
        validate_command("kubectl get pods | grep nginx")  # Should not raise

    def test_dangerous_command(self, strict_security_mode):
        """Dangerous command should fail."""
        with pytest.raises(ValueError):
            validate_command("kubectl delete pods --all")


class TestIsValidK8sTool:
    """Tests for K8s tool validation."""

    def test_kubectl_valid(self):
        assert is_valid_k8s_tool("kubectl") is True

    def test_helm_valid(self):
        assert is_valid_k8s_tool("helm") is True

    def test_argocd_valid(self):
        assert is_valid_k8s_tool("argocd") is True

    def test_unknown_tool_invalid(self):
        assert is_valid_k8s_tool("istioctl") is False

    def test_empty_invalid(self):
        assert is_valid_k8s_tool("") is False


class TestSplitPipeCommand:
    """Tests for pipe command splitting."""

    def test_simple_pipe(self):
        result = split_pipe_command("kubectl get pods | grep nginx")
        assert result == ["kubectl get pods", "grep nginx"]

    def test_multiple_pipes(self):
        result = split_pipe_command("kubectl get pods | grep nginx | wc -l")
        assert result == ["kubectl get pods", "grep nginx", "wc -l"]

    def test_no_pipe(self):
        result = split_pipe_command("kubectl get pods")
        assert result == ["kubectl get pods"]

    def test_pipe_in_quotes_not_split(self):
        result = split_pipe_command("kubectl get pods -l 'app|web'")
        assert len(result) == 1  # Should not split on quoted pipe

    def test_empty_command(self):
        result = split_pipe_command("")
        assert result == [""]

    def test_preserves_whitespace_in_args(self):
        result = split_pipe_command('kubectl get pods -o "jsonpath={.items}"')
        assert len(result) == 1