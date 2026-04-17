#!/usr/bin/env bash
set -euo pipefail

# Run staged LLaMA-Factory training for NLSQLRO on a single node.
#
# Stages:
#   A: external dataset
#   B: RoGov dataset
#   C: optional 80/20 mix (RoGov/external)
#
# Defaults:
#   - prepares datasets/llamafactory
#   - uses 4 GPUs: 0,1,2,3
#   - runs A + B + C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

GPUS="${GPUS:-0,1,2,3}"
OUT_DIR="${OUT_DIR:-datasets/llamafactory}"
PREP_DATA="${PREP_DATA:-1}"
RUN_STAGE_C="${RUN_STAGE_C:-1}"
PREP_ONLY="${PREP_ONLY:-0}"

STAGE_A_CFG="training/llamafactory/sft_stage_a_external_lora.yaml"
STAGE_B_CFG="training/llamafactory/sft_stage_b_rogov_lora.yaml"
STAGE_C_CFG="training/llamafactory/sft_stage_c_mix_lora.yaml"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/train_all.sh [options]

Options:
  --gpus "0,1,2,3"      Comma-separated GPU ids for CUDA_VISIBLE_DEVICES.
  --out-dir <path>      Output directory for prepare-llamafactory.
  --skip-prepare        Skip dataset preparation step.
  --prepare-only        Only prepare datasets, do not train.
  --no-stage-c          Skip optional Stage C mix.
  -h, --help            Show this help.

Env overrides:
  GPUS, OUT_DIR, PREP_DATA, PREP_ONLY, RUN_STAGE_C,
  WANDB_PROJECT, WANDB_ENTITY
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --gpus)
      GPUS="${2:-}"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="${2:-}"
      shift 2
      ;;
    --skip-prepare)
      PREP_DATA=0
      shift
      ;;
    --prepare-only)
      PREP_ONLY=1
      shift
      ;;
    --no-stage-c)
      RUN_STAGE_C=0
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

if ! command -v python >/dev/null 2>&1; then
  echo "python not found in PATH." >&2
  exit 1
fi

if ! command -v llamafactory-cli >/dev/null 2>&1; then
  echo "llamafactory-cli not found in PATH." >&2
  echo "Activate the right env first (e.g. source scripts/activate.sh)." >&2
  exit 1
fi

for cfg in "${STAGE_A_CFG}" "${STAGE_B_CFG}" "${STAGE_C_CFG}"; do
  if [[ ! -f "${cfg}" ]]; then
    echo "Missing config: ${cfg}" >&2
    exit 1
  fi
  if grep -q "/path/to/NLSQLRO/datasets/llamafactory" "${cfg}"; then
    echo "Config still has placeholder dataset_dir: ${cfg}" >&2
    echo "Set dataset_dir to your absolute repo path before training." >&2
    exit 1
  fi
done

if [[ "${PREP_DATA}" == "1" ]]; then
  echo "[prep] Preparing LLaMA-Factory datasets into: ${OUT_DIR}"
  python -m dataset_generator.cli prepare-llamafactory --out-dir "${OUT_DIR}"
fi

if [[ "${PREP_ONLY}" == "1" ]]; then
  echo "[prep] Done (prepare-only mode)."
  exit 0
fi

export FORCE_TORCHRUN=1
export CUDA_VISIBLE_DEVICES="${GPUS}"
export WANDB_PROJECT="${WANDB_PROJECT:-nlsqlro}"

echo "[train] GPUs: ${CUDA_VISIBLE_DEVICES}"
echo "[train] WANDB_PROJECT: ${WANDB_PROJECT}"
if [[ -n "${WANDB_ENTITY:-}" ]]; then
  export WANDB_ENTITY
  echo "[train] WANDB_ENTITY: ${WANDB_ENTITY}"
fi

echo "[train] Stage A"
llamafactory-cli train "${STAGE_A_CFG}"

echo "[train] Stage B"
llamafactory-cli train "${STAGE_B_CFG}"

if [[ "${RUN_STAGE_C}" == "1" ]]; then
  echo "[train] Stage C"
  llamafactory-cli train "${STAGE_C_CFG}"
else
  echo "[train] Stage C skipped."
fi

echo "[train] All requested stages completed."
