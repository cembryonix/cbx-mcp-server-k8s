#!/usr/bin/env bash
set -e

# CBX MCP K8s Server - Docker Build Script

publish_build=false
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load configuration
config_file="${script_dir}/build-config.env"
if [ ! -f "$config_file" ]; then
    echo "Error: Configuration file not found: $config_file"
    exit 1
fi

source "$config_file"

# Validate required variables
required_vars=("gh_username" "docker_image_name" "local_tag" "gh_repo_owner")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "Error: Required variable '$var' is not set in $config_file"
        exit 1
    fi
done

# Read version from version.txt
version_file="${script_dir}/../../version.txt"
if [ ! -f "$version_file" ]; then
    echo "Error: Version file not found: $version_file"
    exit 1
fi
release_tag="$(cat "$version_file" | tr -d '[:space:]')"

# Process arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        publish)
            publish_build=true
            shift
            ;;
        *)
            echo "Unknown argument: $1"
            exit 1
            ;;
    esac
done

# Detect local platform
detect_local_platform() {
    if docker info --format '{{.Architecture}}' >/dev/null 2>&1; then
        case "$(docker info --format '{{.Architecture}}')" in
            x86_64|amd64)  echo "linux/amd64" ;;
            aarch64|arm64) echo "linux/arm64" ;;
            *) echo "Error: Unsupported Docker architecture" >&2; exit 1 ;;
        esac
    else
        case "$(uname -m)" in
            x86_64|amd64)  echo "linux/amd64" ;;
            arm64|aarch64) echo "linux/arm64" ;;
            *) echo "Error: Unsupported architecture '$(uname -m)'" >&2; exit 1 ;;
        esac
    fi
}

# pkg/docker/ is two levels down from project root
root_dir="${script_dir}/../.."

# Cleanup Python compiled files
find "${root_dir}/app/cbx_mcp_k8s" \( -name "*.pyc" -o -name "__pycache__" \) -delete 2>/dev/null || true

# Setup buildx builder
if ! docker buildx inspect cbxbuilder &>/dev/null; then
    echo "Creating buildx builder 'cbxbuilder'..."
    docker buildx create --name cbxbuilder --driver docker-container --bootstrap
fi

docker buildx use cbxbuilder

# Build
if [ "$publish_build" = true ]; then
    if [ -z "$GITHUB_TOKEN" ]; then
        echo "Error: GITHUB_TOKEN environment variable is not set"
        exit 1
    fi

    echo "Logging in to GitHub Container Registry..."
    echo "$GITHUB_TOKEN" | docker login ghcr.io -u "${gh_username}" --password-stdin

    echo "Building and pushing multi-arch image..."
    docker buildx build --platform linux/amd64,linux/arm64 \
        -f "${script_dir}/Dockerfile" \
        -t "ghcr.io/${gh_repo_owner}/${docker_image_name}:${release_tag}" \
        --push \
        "${root_dir}"
else
    local_platform="$(detect_local_platform)"
    echo "Building local image..."
    echo "Platform: ${local_platform}"
    docker buildx build \
        --platform "${local_platform}" \
        -f "${script_dir}/Dockerfile" \
        -t "${docker_image_name}:${local_tag}" \
        --load \
        "${root_dir}"
fi

echo "Build completed successfully!"
