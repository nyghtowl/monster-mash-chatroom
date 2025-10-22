#!/usr/bin/env bash
# shellcheck disable=SC2034
UVICORN_PID=""
# Helper script to bootstrap the local demo: creates the venv, installs
# dependencies, optionally boots the persona workers, launches the Kafka
# stack (if Docker is present), and starts the FastAPI application in reload
# mode.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="${ROOT_DIR}/.venv"
PYTHON_BIN="${VENV_PATH}/bin/python"
PIP_BIN="${VENV_PATH}/bin/pip"
START_WORKERS=false
WORKER_PIDS=()
WORKER_NAMES=(witch vampire ghost werewolf zombie)
# Determine desired Kafka connection details, allowing legacy env fallbacks.
DEFAULT_KAFKA_TOPIC="${BUS__KAFKA__TOPIC:-${KAFKA__TOPIC:-${KAFKA_TOPIC:-monster.chat}}}"
DEFAULT_KAFKA_BROKERS="${BUS__KAFKA__BROKERS:-${KAFKA__BROKERS:-${KAFKA_BROKERS:-localhost:29092}}}"
UVICORN_PORT="${UVICORN_PORT:-8000}"

usage() {
  cat <<'EOF'
Usage: ./run.sh [--with-workers]

Bootstrap the local Monster Mash Chatroom demo. Creates/uses .venv, installs
dependencies, brings up the Kafka-compatible stack via docker compose, and
starts the FastAPI server with auto-reload.

Options:
  --with-workers    Launch persona workers in the background (logs in ./logs).
  -h, --help        Show this message.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-workers)
      START_WORKERS=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[error] Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ ! -d "${VENV_PATH}" ]]; then
  echo "[setup] Creating virtual environment at ${VENV_PATH}" >&2
  python3 -m venv "${VENV_PATH}"
fi

# shellcheck disable=SC1090
source "${VENV_PATH}/bin/activate"

echo "[setup] Ensuring dependencies are installed" >&2
"${PYTHON_BIN}" -m pip install --upgrade pip >/dev/null
"${PIP_BIN}" install -e '.[dev]' >/dev/null

if command -v docker >/dev/null 2>&1; then
  export BUS__BACKEND="kafka"
  if [[ -n "${BUS__KAFKA__BROKERS:-}" && -z "${BUS__KAFKA__BROKERS__0:-}" ]]; then
    export BUS__KAFKA__BROKERS__0="${BUS__KAFKA__BROKERS}"
    unset BUS__KAFKA__BROKERS
  fi
  if [[ -z "${BUS__KAFKA__BROKERS__0:-}" ]]; then
    export BUS__KAFKA__BROKERS__0="${DEFAULT_KAFKA_BROKERS}"
  fi
  if [[ -z "${BUS__KAFKA__TOPIC:-}" ]]; then
    export BUS__KAFKA__TOPIC="${DEFAULT_KAFKA_TOPIC}"
  fi
  KAFKA_TOPIC_FOR_SETUP="${BUS__KAFKA__TOPIC}"

  echo "[setup] Starting Kafka stack via docker compose" >&2
  docker compose up -d --remove-orphans kafka kafka-ui
  echo "[setup] Ensuring topic '${KAFKA_TOPIC_FOR_SETUP}' exists" >&2
  for attempt in {1..10}; do
    if output=$(docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh \
      --create --if-not-exists --topic "${KAFKA_TOPIC_FOR_SETUP}" --bootstrap-server kafka:9092 2>&1); then
      echo "[setup] Topic '${KAFKA_TOPIC_FOR_SETUP}' ready" >&2
      break
    fi
    if echo "${output}" | grep -qi "already exists"; then
      echo "[setup] Topic '${KAFKA_TOPIC_FOR_SETUP}' already exists" >&2
      break
    fi
    if [[ ${attempt} -eq 10 ]]; then
      echo "[warn] Unable to verify topic creation; continuing anyway" >&2
    else
      echo "[setup] Waiting for Kafka (attempt ${attempt}/10)" >&2
      sleep 1
    fi
  done
else
  echo "[warn] Docker not found. Start your Kafka-compatible broker manually." >&2
  if [[ -z "${BUS__KAFKA__BROKERS:-}" ]]; then
    echo "[info] Kafka env vars not set; app will run in in-memory mode." >&2
  fi
fi

if command -v lsof >/dev/null 2>&1; then
  IN_USE_PIDS=$(lsof -ti tcp:"${UVICORN_PORT}" || true)
  if [[ -n "${IN_USE_PIDS}" ]]; then
    echo "[error] Port ${UVICORN_PORT} already in use by process(es): ${IN_USE_PIDS}" >&2
    echo "        Stop the conflicting service or set UVICORN_PORT to an open port." >&2
    exit 1
  fi
else
  echo "[warn] lsof not available; skipping port availability check" >&2
fi

if ${START_WORKERS}; then
  LOG_DIR="${ROOT_DIR}/logs"
  mkdir -p "${LOG_DIR}"
  if compgen -G "${LOG_DIR}/*.log" > /dev/null; then
    echo "[workers] Clearing previous worker logs" >&2
    rm -f "${LOG_DIR}"/*.log
  fi
  echo "[workers] Starting persona workers (logs in ${LOG_DIR})" >&2
  for name in "${WORKER_NAMES[@]}"; do
    LOG_FILE="${LOG_DIR}/${name}.log"
    "${PYTHON_BIN}" -m monster_mash_chatroom.agent_runner "${name}" \
      >>"${LOG_FILE}" 2>&1 &
    pid=$!
    WORKER_PIDS+=("${pid}")
    echo "  - ${name} (pid ${pid}) -> ${LOG_FILE}" >&2
  done
fi

cleanup() {
  if [[ ${#WORKER_PIDS[@]} -gt 0 ]]; then
    echo "[cleanup] Stopping persona workers" >&2
    kill "${WORKER_PIDS[@]}" 2>/dev/null || true
    if command -v pgrep >/dev/null 2>&1; then
      for pid in "${WORKER_PIDS[@]}"; do
        children=$(pgrep -P "${pid}" || true)
        if [[ -n "${children}" ]]; then
          kill "${children}" 2>/dev/null || true
        fi
      done
    fi
    wait "${WORKER_PIDS[@]}" 2>/dev/null || true
  fi
  if [[ -n "${UVICORN_PID}" ]] && ps -p "${UVICORN_PID}" >/dev/null 2>&1; then
    echo "[cleanup] Stopping FastAPI server" >&2
    if command -v pkill >/dev/null 2>&1; then
      pkill -P "${UVICORN_PID}" 2>/dev/null || true
    elif command -v pgrep >/dev/null 2>&1; then
      children=$(pgrep -P "${UVICORN_PID}" || true)
      if [[ -n "${children}" ]]; then
        kill "${children}" 2>/dev/null || true
      fi
    fi
    kill -TERM "${UVICORN_PID}" 2>/dev/null || true
    if kill -0 "${UVICORN_PID}" >/dev/null 2>&1; then
      kill -TERM -"${UVICORN_PID}" 2>/dev/null || true
    fi
    wait "${UVICORN_PID}" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

echo "[run] Launching FastAPI server on http://localhost:${UVICORN_PORT}" >&2
echo "[tips] Open http://localhost:${UVICORN_PORT}/docs to chat; open Kafka UI at http://localhost:8080" >&2
"${PYTHON_BIN}" -m uvicorn monster_mash_chatroom.app:app --host 0.0.0.0 --port "${UVICORN_PORT}" --reload &
UVICORN_PID=$!
wait ${UVICORN_PID}
