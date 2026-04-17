#!/usr/bin/env bash

# Backward-compatible wrapper.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/scripts/activate.sh" "$@"
