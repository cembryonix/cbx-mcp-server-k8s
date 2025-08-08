#!/usr/bin/env bash

set -e  # Exit on any error

# Initialize publish flag
publish_build=false

# Get script directory
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load configuration from external file
config_file="${script_dir}/build-config.env"
if [ ! -f "$config_file" ]; then
    echo "Error: Configuration file not found: $config_file"
    echo "Please create the configuration file with the required variables."
    exit 1
fi

# Source the configuration file
echo "Loading configuration from: $config_file"
source "$config_file"

# Validate required variables are set
required_vars=("gh_username" "docker_image_name" "dev_tag" "release_tag" "release_github_org")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "Error: Required variable '$var' is not set in $config_file"
        exit 1
    fi
done

# Process command line arguments
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

# script is in {root}/pkg/docker/
root_dir="${script_dir}/../.."

## cleanup source code dir
# Remove any Python compiled files which we don't need to copy to image
find ${root_dir}/app/cbx_mcp_k8s \( -name "*.pyc" -o -name "__pycache__" \) -delete 2>/dev/null || true

# Check if the builder already exists
if ! docker buildx inspect cbxbuilder &>/dev/null; then
    echo "Creating new buildx builder 'cbxbuilder'..."
    docker buildx create --name cbxbuilder --driver docker-container --bootstrap
else
    echo "Builder 'cbxbuilder' already exists, using it."
fi

# Use the cbxbuilder
docker buildx use cbxbuilder

# Build with both local and GitHub Container Registry tags if publishing
if [ "$publish_build" = true ]; then
    # Login to GitHub Container Registry
    if [ -z "$GITHUB_TOKEN" ]; then
        echo "Error: GITHUB_TOKEN environment variable is not set"
        echo "Please set it with: export GITHUB_TOKEN=your_github_pat"
        exit 1
    fi

    echo "Logging in to GitHub Container Registry..."
    echo "$GITHUB_TOKEN" | docker login ghcr.io -u "${gh_username}" --password-stdin

    echo "Building with GitHub Container Registry tag and pushing..."
    docker buildx build --platform linux/amd64,linux/arm64 \
        -f ${script_dir}/Dockerfile \
        -t "ghcr.io/${release_github_org}/${docker_image_name}:${release_tag}" \
        --push \
        ${root_dir}
else
    echo "Building with local tag only..."
    docker buildx build --platform linux/arm64 \
        -f $script_dir/Dockerfile \
        -t "${docker_image_name}:${dev_tag}" \
        --load \
        ${root_dir}
fi

echo "Build completed successfully!"