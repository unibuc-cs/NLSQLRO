#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN_SCRIPT="${SCRIPT_DIR}/run_4gpu_translate_and_merge.sh"
CLEAN_SCRIPT="${SCRIPT_DIR}/clean_gpu_mem.sh"

# Main run knobs (forwarded to run_4gpu_translate_and_merge.sh)
GPU_IDS="${GPU_IDS:-0 1 2 3}"
TRANSLATOR="${TRANSLATOR:-madlad}"
DTYPE="${DTYPE:-bfloat16}"
MODE="${MODE:-full}"
RUN_NAME="${RUN_NAME:-madlad_4gpu_full}"
DEMO_TOTAL="${DEMO_TOTAL:-100}"
DEMO_PER_SHARD="${DEMO_PER_SHARD:-20}"
LOG_EVERY="${LOG_EVERY:-50}"
SHOW_PROGRESS="${SHOW_PROGRESS:-1}"
PROGRESS_POLL_SECONDS="${PROGRESS_POLL_SECONDS:-15}"
STATUS_STALE_REPORT_EVERY="${STATUS_STALE_REPORT_EVERY:-4}"
WANDB_ENABLE="${WANDB_ENABLE:-0}"
WANDB_PROJECT="${WANDB_PROJECT:-text2sql-ro-prep}"
WANDB_ENTITY="${WANDB_ENTITY:-}"
WANDB_LOG_EVERY="${WANDB_LOG_EVERY:-20}"
REPORT_GPU_STATE="${REPORT_GPU_STATE:-1}"
FINAL_DATASET_CLEANUP="${FINAL_DATASET_CLEANUP:-1}"
FINAL_CLEANUP_OUTPUT_DIR="${FINAL_CLEANUP_OUTPUT_DIR:-}"
FINAL_CLEANUP_WORKERS="${FINAL_CLEANUP_WORKERS:-}"
FINAL_CLEANUP_VALIDATE_SQL="${FINAL_CLEANUP_VALIDATE_SQL:-1}"
FINAL_CLEANUP_STRICT_SQL_TYPE="${FINAL_CLEANUP_STRICT_SQL_TYPE:-0}"
FINAL_CLEANUP_MAX_LINES="${FINAL_CLEANUP_MAX_LINES:-}"

# Preflight knobs
ENABLE_PREFLIGHT="${ENABLE_PREFLIGHT:-1}"
PREFLIGHT_GPU="${PREFLIGHT_GPU:-0}"
PREFLIGHT_RUN_NAME="${PREFLIGHT_RUN_NAME:-${RUN_NAME}_preflight}"
PREFLIGHT_DEMO_PER_SHARD="${PREFLIGHT_DEMO_PER_SHARD:-5}"
PREFLIGHT_LOG_EVERY="${PREFLIGHT_LOG_EVERY:-1}"
PREFLIGHT_POLL_SECONDS="${PREFLIGHT_POLL_SECONDS:-5}"

usage() {
  cat <<'EOF'
Usage:
  bash run_with_preflight.sh

Environment overrides:
  GPU_IDS="0 1 2 3" TRANSLATOR=madlad DTYPE=bfloat16 MODE=full RUN_NAME=my_run bash run_with_preflight.sh

Preflight controls:
  ENABLE_PREFLIGHT=1            # run single-shard smoke test before main run
  PREFLIGHT_GPU=0               # GPU used for smoke test
  PREFLIGHT_DEMO_PER_SHARD=5    # small dataset size for smoke
  FINAL_DATASET_CLEANUP=1       # run clean_madlad_dataset.py after merge
EOF
}

if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! -f "${MAIN_SCRIPT}" ]]; then
  echo "Missing main script: ${MAIN_SCRIPT}" >&2
  exit 1
fi
if [[ ! -f "${CLEAN_SCRIPT}" ]]; then
  echo "Missing clean script: ${CLEAN_SCRIPT}" >&2
  exit 1
fi

echo "=== Pre-run process cleanup ==="
pkill -f run_4gpu_translate_and_merge.sh 2>/dev/null || true
pkill -f prepare_gretel_text2sql_ro.py 2>/dev/null || true

echo "=== GPU cleanup ==="
bash "${CLEAN_SCRIPT}" --gpus "${GPU_IDS}"

if [[ "${ENABLE_PREFLIGHT}" == "1" ]]; then
  echo "=== Preflight smoke run (single shard) ==="
  rm -f "${SCRIPT_DIR}/${PREFLIGHT_RUN_NAME}"_shard*.log 2>/dev/null || true
  rm -rf "${SCRIPT_DIR}/${PREFLIGHT_RUN_NAME}"_shard* "${SCRIPT_DIR}/${PREFLIGHT_RUN_NAME}_merged" 2>/dev/null || true

  GPU_IDS="${PREFLIGHT_GPU}" \
  TRANSLATOR="${TRANSLATOR}" \
  DTYPE="${DTYPE}" \
  MODE="demo_per_shard" \
  DEMO_PER_SHARD="${PREFLIGHT_DEMO_PER_SHARD}" \
  LOG_EVERY="${PREFLIGHT_LOG_EVERY}" \
  SHOW_PROGRESS="1" \
  PROGRESS_POLL_SECONDS="${PREFLIGHT_POLL_SECONDS}" \
  STATUS_STALE_REPORT_EVERY="2" \
  RUN_NAME="${PREFLIGHT_RUN_NAME}" \
  WANDB_ENABLE="0" \
  REPORT_GPU_STATE="${REPORT_GPU_STATE}" \
  FINAL_DATASET_CLEANUP="${FINAL_DATASET_CLEANUP}" \
  FINAL_CLEANUP_OUTPUT_DIR="${FINAL_CLEANUP_OUTPUT_DIR}" \
  FINAL_CLEANUP_WORKERS="${FINAL_CLEANUP_WORKERS}" \
  FINAL_CLEANUP_VALIDATE_SQL="${FINAL_CLEANUP_VALIDATE_SQL}" \
  FINAL_CLEANUP_STRICT_SQL_TYPE="${FINAL_CLEANUP_STRICT_SQL_TYPE}" \
  FINAL_CLEANUP_MAX_LINES="${FINAL_CLEANUP_MAX_LINES}" \
  CLEANUP_BEFORE_RUN="1" \
  CLEANUP_USER_CUDA="1" \
  bash "${MAIN_SCRIPT}"

  PREFLIGHT_LOG="${SCRIPT_DIR}/${PREFLIGHT_RUN_NAME}_shard0.log"
  if [[ ! -f "${PREFLIGHT_LOG}" ]]; then
    echo "Preflight failed: missing log ${PREFLIGHT_LOG}" >&2
    exit 1
  fi
  if ! grep -qa '^\[stage\].*translator_init_done' "${PREFLIGHT_LOG}"; then
    echo "Preflight failed: translator did not finish init." >&2
    tail -n 120 "${PREFLIGHT_LOG}" || true
    exit 1
  fi
  if ! grep -qaE '^\[progress\].*processed=[1-9][0-9]*' "${PREFLIGHT_LOG}"; then
    echo "Preflight failed: no processed>0 progress seen." >&2
    tail -n 120 "${PREFLIGHT_LOG}" || true
    exit 1
  fi
  echo "Preflight passed."
fi

echo "=== Main run ==="
GPU_IDS="${GPU_IDS}" \
TRANSLATOR="${TRANSLATOR}" \
DTYPE="${DTYPE}" \
MODE="${MODE}" \
RUN_NAME="${RUN_NAME}" \
DEMO_TOTAL="${DEMO_TOTAL}" \
DEMO_PER_SHARD="${DEMO_PER_SHARD}" \
LOG_EVERY="${LOG_EVERY}" \
SHOW_PROGRESS="${SHOW_PROGRESS}" \
PROGRESS_POLL_SECONDS="${PROGRESS_POLL_SECONDS}" \
STATUS_STALE_REPORT_EVERY="${STATUS_STALE_REPORT_EVERY}" \
WANDB_ENABLE="${WANDB_ENABLE}" \
WANDB_PROJECT="${WANDB_PROJECT}" \
WANDB_ENTITY="${WANDB_ENTITY}" \
WANDB_LOG_EVERY="${WANDB_LOG_EVERY}" \
REPORT_GPU_STATE="${REPORT_GPU_STATE}" \
FINAL_DATASET_CLEANUP="${FINAL_DATASET_CLEANUP}" \
FINAL_CLEANUP_OUTPUT_DIR="${FINAL_CLEANUP_OUTPUT_DIR}" \
FINAL_CLEANUP_WORKERS="${FINAL_CLEANUP_WORKERS}" \
FINAL_CLEANUP_VALIDATE_SQL="${FINAL_CLEANUP_VALIDATE_SQL}" \
FINAL_CLEANUP_STRICT_SQL_TYPE="${FINAL_CLEANUP_STRICT_SQL_TYPE}" \
FINAL_CLEANUP_MAX_LINES="${FINAL_CLEANUP_MAX_LINES}" \
bash "${MAIN_SCRIPT}"
