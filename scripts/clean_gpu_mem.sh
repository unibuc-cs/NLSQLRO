#!/usr/bin/env bash
set -euo pipefail

# Standalone GPU cleanup helper.
# Default behavior: kill only CUDA compute PIDs owned by the current user.

GPU_IDS="${GPU_IDS:-}"
ONLY_USER="${ONLY_USER:-1}"
FORCE_KILL="${FORCE_KILL:-1}"
SLEEP_SECONDS="${SLEEP_SECONDS:-2}"
REPORT_GPU_STATE="${REPORT_GPU_STATE:-1}"
KILL_PREP_WORKERS="${KILL_PREP_WORKERS:-1}"

USER_UID="$(id -u)"
USER_NAME="$(id -un)"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/clean_gpu_mem.sh [--gpus "0 1 2 3"] [--all-users] [--no-force] [--no-report]

Options:
  --gpus "..."    Space-separated GPU indices to target.
  --all-users     Kill CUDA PIDs from all users (default is only current user).
  --no-force      Skip SIGKILL pass; only send SIGTERM.
  --no-report     Disable before/after GPU state report.
  -h, --help      Show this help.

Env overrides:
  GPU_IDS, ONLY_USER, FORCE_KILL, SLEEP_SECONDS, REPORT_GPU_STATE, KILL_PREP_WORKERS
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --gpus)
      if [[ $# -lt 2 ]]; then
        echo "--gpus requires a value, e.g. --gpus \"0 1 2 3\"" >&2
        exit 1
      fi
      GPU_IDS="${2:-}"
      shift 2
      ;;
    --all-users)
      ONLY_USER=0
      shift
      ;;
    --no-force)
      FORCE_KILL=0
      shift
      ;;
    --no-report)
      REPORT_GPU_STATE=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "nvidia-smi not found. Nothing to clean."
  exit 0
fi

if [[ -z "${GPU_IDS}" ]]; then
  GPU_IDS="$(nvidia-smi --query-gpu=index --format=csv,noheader,nounits 2>/dev/null | tr -d '\r' | xargs || true)"
fi

if [[ -z "${GPU_IDS}" ]]; then
  echo "No GPUs detected."
  exit 0
fi

read -r -a GPUS <<< "${GPU_IDS}"

report_gpu_state() {
  local title="$1"
  echo "${title}"
  for gpu_id in "${GPUS[@]}"; do
    local mem_line
    mem_line="$(nvidia-smi -i "${gpu_id}" --query-gpu=memory.total,memory.used,memory.free --format=csv,noheader,nounits 2>/dev/null | head -n 1 | tr -d '\r')"
    if [[ -n "${mem_line}" ]]; then
      echo "[gpu ${gpu_id}] total/used/free MiB: ${mem_line}"
    fi

    local proc_lines
    proc_lines="$(nvidia-smi -i "${gpu_id}" --query-compute-apps=pid,used_gpu_memory,process_name --format=csv,noheader,nounits 2>/dev/null | tr -d '\r' | awk 'NF' || true)"
    if [[ -n "${proc_lines}" ]]; then
      echo "[gpu ${gpu_id}] compute apps:"
      echo "${proc_lines}"
    else
      echo "[gpu ${gpu_id}] compute apps: none"
    fi
  done
}

if [[ "${KILL_PREP_WORKERS}" == "1" ]]; then
  echo "Stopping stale prep workers for user '${USER_NAME}'..."
  pkill -u "${USER_UID}" -f "prepare_gretel_text2sql_ro.py" 2>/dev/null || true
  pkill -u "${USER_UID}" -f "run_4gpu_translate_and_merge.sh" 2>/dev/null || true
fi

if [[ "${REPORT_GPU_STATE}" == "1" ]]; then
  report_gpu_state "GPU state before cleanup:"
fi

killed_pids=()
for gpu_id in "${GPUS[@]}"; do
  mapfile -t gpu_pids < <(
    nvidia-smi -i "${gpu_id}" --query-compute-apps=pid --format=csv,noheader,nounits 2>/dev/null \
      | tr -d '\r' \
      | awk 'NF' \
      | sort -u
  )
  for pid in "${gpu_pids[@]}"; do
    [[ "${pid}" =~ ^[0-9]+$ ]] || continue
    [[ "${pid}" == "$$" ]] && continue

    owner_uid="$(ps -o uid= -p "${pid}" 2>/dev/null | xargs || true)"
    if [[ -z "${owner_uid}" ]]; then
      continue
    fi
    if [[ "${ONLY_USER}" == "1" ]] && [[ "${owner_uid}" != "${USER_UID}" ]]; then
      continue
    fi

    cmd="$(ps -o cmd= -p "${pid}" 2>/dev/null || true)"
    echo "Stopping CUDA PID ${pid} on GPU ${gpu_id}: ${cmd}"
    kill "${pid}" 2>/dev/null || true
    killed_pids+=("${pid}")
  done
done

if [[ "${#killed_pids[@]}" -eq 0 ]]; then
  if [[ "${ONLY_USER}" == "1" ]]; then
    echo "No user-owned CUDA PIDs found on target GPUs."
  else
    echo "No CUDA PIDs found on target GPUs."
  fi
  if [[ "${REPORT_GPU_STATE}" == "1" ]]; then
    report_gpu_state "GPU state after cleanup:"
  fi
  exit 0
fi

sleep "${SLEEP_SECONDS}"

if [[ "${FORCE_KILL}" == "1" ]]; then
  for pid in "${killed_pids[@]}"; do
    if kill -0 "${pid}" 2>/dev/null; then
      echo "Force killing PID ${pid}"
      kill -9 "${pid}" 2>/dev/null || true
    fi
  done
fi

if [[ "${REPORT_GPU_STATE}" == "1" ]]; then
  report_gpu_state "GPU state after cleanup:"
fi
