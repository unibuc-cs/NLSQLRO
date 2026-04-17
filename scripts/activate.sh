#!/usr/bin/env bash

# Activate repo virtual environment from anywhere.
# Must be sourced, not executed:
#   source scripts/activate.sh

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "This script must be sourced."
  echo "Use: source scripts/activate.sh"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ACTIVATE_PATH="${REPO_ROOT}/.venv/bin/activate"

if [[ -f "${ACTIVATE_PATH}" ]]; then
  # shellcheck disable=SC1090
  source "${ACTIVATE_PATH}"
  export NLSQLRO_ENV_DIR="$(cd "$(dirname "${ACTIVATE_PATH}")/.." && pwd)"
  echo "[activate] using env: ${NLSQLRO_ENV_DIR}"
  return 0
fi

echo "Virtual environment not found at:"
echo "  ${ACTIVATE_PATH}"
echo "Create it first (expected env name is .venv)."
return 1
