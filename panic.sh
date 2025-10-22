#!/usr/bin/env bash
# Emergency "red button" script to stop the Monster Mash Chatroom stack.
set -euo pipefail

log() {
  echo "[panic] $1" >&2
}

log "Initiating emergency shutdown"

if pkill -f "monster_mash_chatroom.agent_runner" >/dev/null 2>&1; then
  log "Stopped persona workers"
else
  log "No persona workers detected"
fi

if pkill -f "uvicorn .*monster_mash_chatroom.app" >/dev/null 2>&1 || pkill -f "python -m uvicorn" >/dev/null 2>&1; then
  log "Stopped FastAPI server"
else
  log "FastAPI server not running"
fi

if pkill -f "watchfiles" >/dev/null 2>&1; then
  log "Stopped autoreload watchers"
fi

if pkill -f "run.sh" >/dev/null 2>&1; then
  log "Terminated run.sh helpers"
fi

if command -v docker >/dev/null 2>&1; then
  if docker compose down >/dev/null 2>&1; then
    log "Docker compose stack stopped"
  else
    log "Docker compose not running or already stopped"
  fi
else
  log "Docker not available; skipped compose teardown"
fi

log "Emergency shutdown complete"
