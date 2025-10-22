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

# Force-kill any Python/uvicorn process still using port 8000 (but not Docker)
if lsof -ti tcp:8000 >/dev/null 2>&1; then
  for pid in $(lsof -ti tcp:8000); do
    # Only kill if it's a Python process
    if ps -p "$pid" -o comm= | grep -q python; then
      kill -9 "$pid" 2>/dev/null && log "Force-killed Python process $pid on port 8000"
    fi
  done
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
  
  # Check for other containers using port 8000
  if docker ps --format "{{.Names}}" | grep -v "monster-chat" | xargs -I {} docker port {} 2>/dev/null | grep -q "8000"; then
    log "Warning: Non-monster-chat containers found using port 8000"
    log "Run 'docker ps' to see them, or use UVICORN_PORT=8001 ./run.sh"
  fi
else
  log "Docker not available; skipped compose teardown"
fi

log "Emergency shutdown complete"
