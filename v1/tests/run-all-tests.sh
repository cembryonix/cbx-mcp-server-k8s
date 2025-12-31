#!/usr/bin/env bash
#
# Run all tests for CBX MCP Server
# Usage: ./tests/run-all-tests.sh
#

set -e

# Get script directory and repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/.."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track results
UNIT_RESULT=0
VALIDATION_RESULT=0

echo "========================================"
echo "CBX MCP Server - Test Suite"
echo "========================================"
echo ""

# Activate virtual environment if it exists
if [ -d "${ROOT_DIR}/venv" ]; then
    echo "Activating virtual environment..."
    source "${ROOT_DIR}/venv/bin/activate"
fi

# Change to repo root
cd "${ROOT_DIR}"

# ------------------------------
# 1. Unit Tests (pytest)
# ------------------------------
echo ""
echo "========================================"
echo -e "${YELLOW}Running Unit Tests...${NC}"
echo "========================================"
echo ""

if python -m pytest tests/unit/ -v --tb=short; then
    echo ""
    echo -e "${GREEN} Unit tests passed${NC}"
    UNIT_RESULT=0
else
    echo ""
    echo -e "${RED} Unit tests failed${NC}"
    UNIT_RESULT=1
fi

# ------------------------------
# 2. Validation Tests (CI mode)
# ------------------------------
echo ""
echo "========================================"
echo -e "${YELLOW}Running Validation Tests (CI mode)...${NC}"
echo "========================================"
echo ""

if python tests/validation/validation-mcp-client.py ci \
    --server-cmd "python app/main.py --config-dir tests/server-configs/stdio"; then
    echo ""
    echo -e "${GREEN} Validation tests passed${NC}"
    VALIDATION_RESULT=0
else
    echo ""
    echo -e "${RED} Validation tests failed${NC}"
    VALIDATION_RESULT=1
fi

# ------------------------------
# Summary
# ------------------------------
echo ""
echo "========================================"
echo "Test Summary"
echo "========================================"
echo ""

if [ $UNIT_RESULT -eq 0 ]; then
    echo -e "  Unit Tests:       ${GREEN}PASSED${NC}"
else
    echo -e "  Unit Tests:       ${RED}FAILED${NC}"
fi

if [ $VALIDATION_RESULT -eq 0 ]; then
    echo -e "  Validation Tests: ${GREEN}PASSED${NC}"
else
    echo -e "  Validation Tests: ${RED}FAILED${NC}"
fi

echo ""

# Exit with failure if any test failed
if [ $UNIT_RESULT -ne 0 ] || [ $VALIDATION_RESULT -ne 0 ]; then
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
else
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
fi