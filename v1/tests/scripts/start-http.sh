#!/bin/bash

# Default config name
CONFIG_NAME="http"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --config-name)
            CONFIG_NAME="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--config-name <config_name>]"
            exit 1
            ;;
    esac
done

# Check where we are and set the root of repo
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# this script is in {root}/tests/scripts/
root_dir="${script_dir}/../.."

# Check if virtual environment exists and activate it
if [ -d "${root_dir}/venv" ]; then
    echo "Activating virtual environment..."
    source ${root_dir}/venv/bin/activate
fi

# Load environment variables if .env exists
if [ -f .env ]; then
    echo "Loading environment variables from .env..."
    export $(cat .env | grep -v '#' | xargs)
fi

# Set up PYTHONPATH to include the app directory
export PYTHONPATH="${PYTHONPATH}:$(pwd)/app"

# Set config directory based on config name
CONFIG_DIR="${script_dir}/../server-configs/${CONFIG_NAME}"

# Display startup information
echo "Starting CBX MCP Server with '$CONFIG_NAME' configuration..."
echo "Using config from: $CONFIG_DIR"
echo "Press Ctrl+C to stop the server"

# Start the server with the appropriate config directory
python3 "${root_dir}/app/main.py" --config-dir "$CONFIG_DIR"